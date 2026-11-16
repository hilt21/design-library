"""Compare watched upstream files at two commits without changing adopted versions."""
import argparse
import json
import subprocess
from pathlib import Path

from tools.export import ROOT, as_json


def compare(entry, checkout, candidate_ref):
    def git(*args):
        return subprocess.check_output(['git','-C',str(checkout),*args],text=True).strip()
    source=entry['source']
    baseline=git('rev-parse',source['commit']+'^{commit}')
    candidate=git('rev-parse',candidate_ref+'^{commit}')
    paths=source.get('watch_paths',[source['path']])
    changed=git('diff','--name-status',baseline,candidate,'--',*paths).splitlines()
    return {'entry_id':entry['id'],'repository':source['repository'], 'adopted_commit':baseline,
            'candidate_commit':candidate,'changed_files':changed, 'affected_cases':entry['cases'] if changed else [],
            'review_status':'needs-review' if changed else 'unchanged'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entry',required=True)
    parser.add_argument('--checkout',type=Path,required=True)
    parser.add_argument('--ref',required=True)
    args=parser.parse_args()
    entries=as_json(ROOT/'catalog.json')['entries']
    entry=next((e for e in entries if e['id']==args.entry),None)
    if entry is None: parser.error('Unknown entry')
    print(json.dumps(compare(entry,args.checkout,args.ref),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
