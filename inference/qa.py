"""Matched-prior calibration and public identifiability diagnostics, never blind truth."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import hashlib
import json
from math import fsum, log, sqrt
from pathlib import Path
from random import Random
import platform

import numpy as np
from physics import load_case, solve, SolverConfig
from .m2 import sample, normalize, aerodynamics, SamplingFailure
from .baseline import ballistic_fit
from .report import summarize

PLAN = Path(__file__).with_name('qa-plan.json')
CURVE = 'goff2026_trionda_b'


def vector(parameters):
    return [*parameters['v0'], parameters.get('cd', parameters.get('cd_anchor')),
            *([parameters['cy'], parameters['cz']] if 'cy' in parameters else [])]


def prior(rng, model):
    p = aerodynamics(rng, model, .08, .27, .22)
    p['v0'] = (rng.uniform(8, 48), rng.uniform(-20, 20), rng.uniform(0, 20))
    if model == 'M3':
        p.update(cd_anchor=p.pop('cd'), curve=CURVE, reference_speed_m_s=30)
    return p


def calibration_job(job):
    model, index, plan = job
    offset = 10000 * int(model[-1]) + index
    rng = Random(plan['generation_seed'] + offset)
    case = load_case()
    config = SolverConfig(horizon_s=case.times[-1])
    generation_rejected = 0
    for _ in range(100000):
        true = prior(rng, model)
        result = solve(model, case, true, config)
        if result.event.event != 'NUMERICAL_FAILURE' and all(result.observation_valid):
            break
        generation_rejected += 1
    else:
        raise RuntimeError('Prior support generation exhausted')
    observed = tuple(tuple(q + rng.gauss(0, plan['sigma_m']) for q in row)
                     for row in result.observations)
    case = replace(case, observations=observed)
    record = dict(model=model, case_index=index, true_parameters=vector(true),
                  observations=observed, generation_rejected=generation_rejected, attempts=[])
    for budget in (plan['draw_budget'], plan['recovery_budget']):
        audit = {}
        try:
            draws, _, _ = sample(case, plan['sigma_m'], budget, plan['inference_seed'] + offset,
                                 model, CURVE if model == 'M3' else None, 0, .27, .22, audit)
            weights = np.asarray(normalize(draws))
        except RuntimeError as exc:
            record.update(error=str(exc), sampling=audit)
            return record
        ess = 1 / float(weights @ weights)
        record['attempts'].append(dict(budget=budget, ess=ess, sampling=audit))
        if ess >= plan['minimum_ess']:
            break
    values = np.array([vector(p) for _, _, p in draws])
    ranks = np.sum(weights[:, None] * (values < vector(true)), axis=0)
    record.update(ess=ess, max_weight=float(weights.max()), ranks=ranks.tolist(),
                  covered_95=((ranks >= .025) & (ranks <= .975)).tolist())
    return record


def calibration(plan, output, workers):
    jobs = [(model, index, plan) for model in plan['models'] for index in range(plan['cases_per_model'])]
    records = []
    with ProcessPoolExecutor(workers) as pool, (output/'calibration-cases.jsonl').open('w') as stream:
        for record in pool.map(calibration_job, jobs, chunksize=1):
            records.append(record)
            stream.write(json.dumps(record) + '\n')
            stream.flush()
            print(record['model'], record['case_index'], record.get('ess', record.get('error')), flush=True)
    family_size = sum(4 if m == 'M1' else 6 for m in plan['models'])
    summaries = {}
    for model in plan['models']:
        group = [r for r in records if r['model'] == model]
        usable = [r for r in group if 'ranks' in r]
        n = len(usable)
        if not n:
            summaries[model] = dict(status='failed', cases=len(group), failures=len(group))
            continue
        ranks = np.sort(np.array([r['ranks'] for r in usable]), axis=0)
        ks = np.maximum(np.max(np.arange(1, n+1)[:, None]/n-ranks, axis=0),
                        np.max(ranks-np.arange(n)[:, None]/n, axis=0))
        bound = sqrt(log(2*family_size/plan['rank_family_alpha'])/(2*n))
        low = sum(r['ess'] < plan['minimum_ess'] for r in usable)
        passed = len(usable) == len(group) and low == 0 and bool(np.all(ks <= bound))
        summaries[model] = dict(status='passed_screen' if passed else 'not_certified', cases=len(group),
            failures=len(group)-n, low_ess=low, ks=ks.tolist(), simultaneous_dkw_bound=bound,
            coverage_95=np.mean([r['covered_95'] for r in usable], axis=0).tolist(),
            minimum_ess=min(r['ess'] for r in usable), maximum_weight=max(r['max_weight'] for r in usable))
    return summaries


def fit_velocity(case, aero, start):
    v = np.array(start, dtype=float)
    for _ in range(12):
        result = solve('M2', case, dict(aero, v0=v), SolverConfig(horizon_s=case.times[-1]))
        if not all(result.observation_valid):
            return None
        residual = np.array(result.observations).ravel() - np.array(case.observations).ravel()
        columns = []
        for d in np.eye(3)*1e-4:
            hi = solve('M2', case, dict(aero, v0=v+d), SolverConfig(horizon_s=case.times[-1]))
            lo = solve('M2', case, dict(aero, v0=v-d), SolverConfig(horizon_s=case.times[-1]))
            if not all(hi.observation_valid) or not all(lo.observation_valid):
                return None
            columns.append((np.array(hi.observations).ravel()-np.array(lo.observations).ravel())/2e-4)
        step = np.linalg.lstsq(np.array(columns).T, residual, rcond=None)[0]
        v -= step
        if np.linalg.norm(step) < 1e-9:
            break
    if not (8 < v[0] < 48 and -20 < v[1] < 20 and 0 < v[2] < 20):
        return None
    return dict(aero, v0=v.tolist())


def public_diagnostics(plan, output):
    case = load_case()
    draws, _, _ = sample(case, .01, plan['public_draws'], plan['public_seed'], 'M2', None, 0, .27, .22)
    weights = np.asarray(normalize(draws))
    values = np.array([vector(p) for _, _, p in draws])
    rng = Random(plan['generation_seed'])
    prior_values = np.array([vector(prior(rng, 'M2')) for _ in range(plan['prior_draws_for_contraction'])])
    posterior_cov = np.cov(values.T, aweights=weights, ddof=0)
    prior_sd = np.std(prior_values, axis=0)
    sd = np.sqrt(np.diag(posterior_cov))
    # Highest posterior density, not highest importance weight, chooses the reference fit.
    def log_target(p):
        fit = solve('M2', case, p, SolverConfig(horizon_s=case.times[-1]))
        residual = (np.asarray(fit.observations)-case.observations)/.01
        return -.5*np.sum(residual**2)-.5*((p['cd']-.27)/.14)**2-.5*(p['cy']**2+p['cz']**2)/.22**2
    best = max((p for _, _, p in draws), key=log_target)
    reference = np.array(vector(best))
    def obs(theta):
        p = dict(v0=theta[:3], cd=theta[3], cy=theta[4], cz=theta[5])
        return np.asarray(solve('M2', case, p, SolverConfig(horizon_s=case.times[-1])).observations).ravel()
    def jac(step):
        return np.column_stack([(obs(reference+d)-obs(reference-d))/(2*step*.01)
                                for d in np.diag(prior_sd*step)])
    matrix = jac(1e-4)
    q, _ = np.linalg.qr(matrix[:, :3])
    projected = matrix[:, 3:] - q @ (q.T @ matrix[:, 3:])
    _, singular, directions = np.linalg.svd(projected)
    profiles = []
    for direction_index in (-1, -2):
        direction = directions[direction_index]
        for distance in plan['profile_grid']:
            aero = reference[3:] + distance * prior_sd[3:] * direction
            row = dict(direction=direction_index, distance_prior_sd=distance, aerodynamic_parameters=aero.tolist())
            if not (.08 < aero[0] < .55 and aero[1]**2+aero[2]**2 < .55**2):
                row['status'] = 'outside_prior_support'
            else:
                fitted = fit_velocity(case, dict(zip(('cd','cy','cz'), aero)), reference[:3])
                if fitted is None:
                    row['status'] = 'velocity_profile_unavailable'
                else:
                    event = solve('M2', case, fitted)
                    row.update(status='ok', parameters=fitted, event=asdict(event.event),
                        whitened_residual_norm=float(np.linalg.norm((np.array(event.observations)-case.observations)/.01)))
            profiles.append(row)
    # Fixed parameter convergence independent of Monte Carlo repetitions.
    numerical = []
    for index in np.linspace(0, len(draws)-1, 64, dtype=int):
        p = draws[index][2]
        a = solve('M2', case, p).event
        b = solve('M2', case, p, SolverConfig(max_step_s=.005)).event
        numerical.append(dict(same_event=a.event == b.event,
            time_difference_s=abs(a.t_s-b.t_s) if a.t_s is not None and b.t_s is not None else None,
            position_difference_m=max(abs(a.y_m-b.y_m), abs(a.z_m-b.z_m)) if a.y_m is not None and b.y_m is not None else None))
    def summary(ds, ws):
        rows=[]
        for (_, _, p), w in zip(ds, ws):
            e=asdict(solve('M2',case,p).event)
            rows.append(dict(weight=str(w), **{k: '' if v is None else str(int(v)) if isinstance(v,bool) else str(v) for k,v in e.items()}))
        return summarize(rows,case)
    first = summary(draws,weights)
    repeated, _, _ = sample(case,.01,plan['public_repeat_draws'],plan['public_seed']+1,'M2',None,0,.27,.22)
    second = summary(repeated,normalize(repeated))
    interval_diff=max(abs(a-b) for k in ('y_m','z_m') for a,b in zip(first['plane_intervals'][k],second['plane_intervals'][k]))
    mode_diff=float(np.linalg.norm(np.array(first['entry_mode_yz_m'])-second['entry_mode_yz_m']))
    event_diff=max(abs(first[k]-second[k]) for k in ('p_reach','p_goal','p_clearance_goal'))
    result=dict(parameter_order=['vx','vy','vz','cd','cy','cz'],prior_sd=prior_sd.tolist(),
        posterior_sd=sd.tolist(),sd_ratio=(sd/prior_sd).tolist(),
        posterior_correlation=(posterior_cov/np.outer(sd,sd)).tolist(),
        reference_parameters=best,reference_method='highest posterior density among importance draws',
        projected_aero_singular_values=singular.tolist(),weak_directions=directions[-2:].tolist(),
        jacobian_step_max_difference=float(np.max(np.abs(matrix-jac(5e-5)))),profiles=profiles,
        fixed_parameter_convergence=numerical,first=first,repeat=second,
        stability=dict(max_event_difference=event_diff,max_interval_difference_m=interval_diff,
                       mode_difference_m=mode_diff,passed=event_diff<=.01 and interval_diff<=.03 and mode_diff<=.1))
    (output/'identifiability.json').write_text(json.dumps(result,indent=2)+'\n')
    return result['stability']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--part',choices=('all','calibration','public'),default='all')
    parser.add_argument('--public-budget-multiplier',type=int,choices=(1,2),default=1)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PLAN.read_text())
    plan['public_draws'] *= args.public_budget_multiplier
    plan['public_repeat_draws'] *= args.public_budget_multiplier
    manifest=dict(plan=plan,plan_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),python=platform.python_version(),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('inference','physics') for p in Path(folder).glob('*.py')})
    if args.part in ('all','calibration'):
        manifest['calibration']=calibration(plan,args.output,args.workers)
    if args.part in ('all','public'):
        manifest['public_stability']=public_diagnostics(plan,args.output)
    manifest['public_budget_multiplier'] = args.public_budget_multiplier
    (args.output/f'{args.part}-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    main()
