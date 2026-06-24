#!/usr/bin/env python3
"""
Create evaluation results JSON file from terminal output
This script helps convert evaluation output to JSON format for HTML display
"""

import json
import argparse
import re


def parse_eval_output_from_text(text):
    """
    Parse evaluation results from text output
    """
    results = {}
    
    # Parse Execution Accuracy (EX)
    ex_match = re.search(r'ACCURACY.*?\n.*?accuracy\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', text, re.DOTALL)
    count_match = re.search(r'count\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', text)
    
    if ex_match and count_match:
        results['ex'] = {
            'simple': {
                'count': int(count_match.group(1)),
                'accuracy': float(ex_match.group(1))
            },
            'moderate': {
                'count': int(count_match.group(2)),
                'accuracy': float(ex_match.group(2))
            },
            'challenging': {
                'count': int(count_match.group(3)),
                'accuracy': float(ex_match.group(3))
            },
            'total': {
                'count': int(count_match.group(4)),
                'accuracy': float(ex_match.group(4))
            }
        }
    
    # Parse VES
    ves_match = re.search(r'VES.*?\n.*?ves\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', text, re.DOTALL)
    
    if ves_match and count_match:
        results['ves'] = {
            'simple': {
                'count': int(count_match.group(1)),
                'ves': float(ves_match.group(1))
            },
            'moderate': {
                'count': int(count_match.group(2)),
                'ves': float(ves_match.group(2))
            },
            'challenging': {
                'count': int(count_match.group(3)),
                'ves': float(ves_match.group(3))
            },
            'total': {
                'count': int(count_match.group(4)),
                'ves': float(ves_match.group(4))
            }
        }
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Create evaluation results JSON from values')
    parser.add_argument('--output', '-o', type=str, required=True,
                        help='Output JSON file path')
    
    # EX arguments
    parser.add_argument('--ex-simple-count', type=int, default=0)
    parser.add_argument('--ex-simple-acc', type=float, default=0)
    parser.add_argument('--ex-moderate-count', type=int, default=0)
    parser.add_argument('--ex-moderate-acc', type=float, default=0)
    parser.add_argument('--ex-challenging-count', type=int, default=0)
    parser.add_argument('--ex-challenging-acc', type=float, default=0)
    parser.add_argument('--ex-total-count', type=int, default=0)
    parser.add_argument('--ex-total-acc', type=float, default=0)
    
    # VES arguments
    parser.add_argument('--ves-simple-count', type=int, default=0)
    parser.add_argument('--ves-simple-score', type=float, default=0)
    parser.add_argument('--ves-moderate-count', type=int, default=0)
    parser.add_argument('--ves-moderate-score', type=float, default=0)
    parser.add_argument('--ves-challenging-count', type=int, default=0)
    parser.add_argument('--ves-challenging-score', type=float, default=0)
    parser.add_argument('--ves-total-count', type=int, default=0)
    parser.add_argument('--ves-total-score', type=float, default=0)
    
    args = parser.parse_args()
    
    results = {}
    
    # Build EX results
    if args.ex_total_count > 0:
        results['ex'] = {
            'simple': {
                'count': args.ex_simple_count,
                'accuracy': args.ex_simple_acc
            },
            'moderate': {
                'count': args.ex_moderate_count,
                'accuracy': args.ex_moderate_acc
            },
            'challenging': {
                'count': args.ex_challenging_count,
                'accuracy': args.ex_challenging_acc
            },
            'total': {
                'count': args.ex_total_count,
                'accuracy': args.ex_total_acc
            }
        }
    
    # Build VES results
    if args.ves_total_count > 0:
        results['ves'] = {
            'simple': {
                'count': args.ves_simple_count,
                'ves': args.ves_simple_score
            },
            'moderate': {
                'count': args.ves_moderate_count,
                'ves': args.ves_moderate_score
            },
            'challenging': {
                'count': args.ves_challenging_count,
                'ves': args.ves_challenging_score
            },
            'total': {
                'count': args.ves_total_count,
                'ves': args.ves_total_score
            }
        }
    
    # Save to file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4)
    
    print(f"✅ Evaluation results saved to: {args.output}")


if __name__ == '__main__':
    main()

