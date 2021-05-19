rm build -r -Force
cfn generate
cfn submit --dry-run
sam local invoke TestEntrypoint --event ./src/eq_monitor_nagios/create.json -d 5890

