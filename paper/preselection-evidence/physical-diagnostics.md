# Physical checks for the v1 manuscript review

From the project directory run the following with a checkout that contains the v1 release and the locked public selection prediction bundle unpacked.

    python -B -m physics.audit_frozen_v1 . WP2_CHECKOUT/inference/selection-v1/predictions.csv.gz

The script verifies the decompressed selection prediction digest against the v1 lock and the candidate JSON against the release manifest. It ran on both the original v1 checkout and the latest repository archive and produced byte-identical JSON.

| Evidence type | Model | Arrival after launch, s | Time after second frame, s |
|---|---|---:|---:|
| Point fit | B0 | 0.370620 | 0.270620 |
| Point fit | B1 | 0.405008 | 0.305008 |
| Frozen candidate median given plane arrival | M1 | 0.400273 | 0.300273 |
| Frozen candidate median given plane arrival | M2 | 0.396896 | 0.296896 |
| Fixed B0 launch velocity, Cd sweep 0.15–0.45 | M1 | 0.388716–0.428512 | 0.288716–0.328512 |

The sweep uses increments of 0.01 and the supplied shot's B0 point-fit initial velocity. The center scenario Cd=0.27 arrives at 0.404033 s. The initial drag acceleration magnitude is 14.656 m/s² and its forward component is about 13.7 m/s². Halving the solver step preserved the event and changed arrival times by at most \(6.0\times10^{-10}\) s. This sensitivity intentionally does not refit the frame positions as Cd changes. It gives no probabilities and cannot establish the true kick arrival time.

The full selection forecast contained 86 completely failed M3 cases across the 260 public selection inputs. The first reported rejected trial evaluation exceeded the Trionda upper knot in 81 cases, at Re=495806–558275 versus an upper knot of 495800. The other five failed for lack of finite posterior weight. These reasons describe trial evaluations. The public locked forecasts do not include the private case-stratum mapping, so the aggregate trigger audit does not assign the 81 cases to individual core strata. The existing frozen aggregate provides 76 fully failed cases among 240 core cases. A single trial evaluation can invalidate the likelihood fit in the locked implementation.

For the deterministic supplied-kick check, both strict curves accepted the full integration using the B0 point-fit launch velocity, Cd anchor 0.27, and zero wind and transverse force. The recorded trace Re ranges were 392480–471436 for Trionda and 389535–471436 for Jabulani, within the respective digitized intervals 100900–495800 and 99900–495800. The 30 m/s anchor corresponds to Re=446685. Anchoring applies a vertical offset to Cd and leaves the Reynolds knots fixed. The resulting force change can change subsequent velocities, but the anchor Re rules out an out-of-domain anchor evaluation for the released configuration. The deterministic check cannot establish support for every posterior draw.

The new diagnostic numbers remain outside manuscript prose pending a frozen diagnostic artifact and claims entries. The T2 and abstract editor can use the supplied claims mapping after the selected run is released.
