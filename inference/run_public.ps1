param(
    [string]$Output = 'inference/wp2-public',
    [int]$Draws = 4000,
    [int]$Seed = 2026
)

$scenarios = [ordered]@{
    m2 = @('--scenario', 'gaussian-10mm')
    m1 = @('--model', 'M1')
    trionda = @('--model', 'M3', '--curve', 'goff2026_trionda_b')
    jabulani = @('--model', 'M3', '--curve', 'goff2026_jabulani_b')
    wind = @('--wind-y', '3')
    'drag-prior' = @('--drag-mean', '0.35')
    'transverse-prior' = @('--transverse-sigma', '0.12')
    sigma5 = @('--sigma-mm', '5')
    sigma20 = @('--sigma-mm', '20')
    rounded = @('--rounded')
}

foreach ($name in $scenarios.Keys) {
    $options = $scenarios[$name]
    if ($name -ne 'm2') {
        $options += @('--scenario', $name)
    }
    python -B -m inference.m2 (Join-Path $Output $name) --draws $Draws --seed $Seed @options
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
python -B -m inference.m2 (Join-Path $Output rounding) --draws (4 * $Draws) --seed $Seed --rounded --sigma-mm 0 --scenario rounding-10mm
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$repeat = "$Output-repeat"
python -B -m inference.m2 $repeat --draws (2 * $Draws) --seed ($Seed + 1)
if ($LASTEXITCODE) { exit $LASTEXITCODE }
python -B -m inference.report $Output --repeat $repeat
exit $LASTEXITCODE
