# Enable TCC mode for Tesla P4
$log = "C:\Users\Best\tcc_setup.log"
nvidia-smi -g 0 -dm 0 > $log 2>&1
nvidia-smi >> $log 2>&1
Get-Content $log
