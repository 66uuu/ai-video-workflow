param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Query,
    [switch]$VideoOnly,
    [int]$Limit = 12
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$args = @((Join-Path $root 'skill_router.py'), 'search', $Query, '--limit', $Limit)
if ($VideoOnly) { $args += '--video-only' }
python @args
