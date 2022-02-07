from typing import Counter
import pandas as pd


audit_files_path = input('Full path for audit files (default path in Linux /var/log/audit/audit.log): ')
audit_file = open(audit_files_path, 'r')

#get all types
exes = []
for line in audit_file:
    if 'key="mdatp"' and 'type=SYSCALL' in line:
        split = line.split(' ')
        exes.append(split[25])

count = Counter(exes)
dict = dict(count)
df = pd.DataFrame(list(dict.items()), columns = ['Process','Count'])
df.sort_values("Count", axis=0, ascending=False,inplace=True, na_position='first')
df['Process'] = df['Process'].str.replace('exe=', '')

print(df.to_string(index=False))