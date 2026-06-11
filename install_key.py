import paramiko
import os

key_path = os.path.expanduser('~/.ssh/id_rsa.pub')
with open(key_path) as f:
    pubkey = f.read().strip()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('194.67.112.4', username='best', password='', timeout=10)

cmd = f'mkdir -p ~/.ssh && echo "{pubkey}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
stdin, stdout, stderr = client.exec_command(cmd)
err = stderr.read().decode()
if err:
    print('STDERR:', err)
print('STDOUT:', stdout.read().decode())

stdin2, stdout2, stderr2 = client.exec_command('hostname')
print('Hostname:', stdout2.read().decode().strip())

client.close()
print('Done')
