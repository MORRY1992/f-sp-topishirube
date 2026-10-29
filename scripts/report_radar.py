"""Report collection, classification and publication separately, then signal health."""
import argparse
import json
from pathlib import Path


def report(queue, editorial, collector_result):
    health = editorial['health']
    counts = editorial['counts']
    lines = [
        '## Official news radar',
        f"Collection health: **{health['status']}**",
        f"Listing endpoints: {health['sourcesOk']}/{health['sourcesTotal']} healthy",
        'A partial company feed does not restore the main listing or PDF monitors.',
        '',
    ]
    for source in queue['sources']:
        lines.append(f"- {source['sourceId']}: {source['status']} / matches: {source.get('candidateCount', 'unknown')} / HTTP: {source.get('httpStatus', source['status'])}")
        if source.get('parserWarning'):
            lines.append('  - Parser warning: zero matches are not proof of no news.')
    lines += [
        '',
        f"Source monitor failures: {len(health['monitorFailures'])}",
        'Classification (unverified): '+json.dumps(counts, ensure_ascii=False),
        'Articles published by this workflow: **0**. Body/date/duplicate/rights review is required.',
        'Fetch failures, stale data and zero matches are NOT no-news results.',
        '',
    ]
    return '\n'.join(lines), 0 if health['status'] == 'ok' and collector_result == 0 else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--queue', type=Path, required=True)
    p.add_argument('--editorial', type=Path, required=True)
    p.add_argument('--collector-result', type=int, required=True)
    p.add_argument('--summary', type=Path)
    args = p.parse_args()
    text, code = report(json.loads(args.queue.read_text()), json.loads(args.editorial.read_text()), args.collector_result)
    print(text)
    if args.summary:
        with args.summary.open('a') as f:
            f.write(text)
    if code:
        print('::warning::Radar is incomplete; saved candidates are unverified. See source health, not just job completion.')
    raise SystemExit(code)
