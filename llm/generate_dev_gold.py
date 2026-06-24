#!/usr/bin/env python3
"""
Generate dev_gold.sql from dev.json
Extract SQL and db_id from dev.json and create the ground truth SQL file
"""

import json
import argparse
import os


def generate_dev_gold(input_json_path, output_sql_path):
    """
    Generate dev_gold.sql file from dev.json
    
    Args:
        input_json_path: Path to dev.json file
        output_sql_path: Path to output dev_gold.sql file
    """
    # Read dev.json
    print(f"📖 Reading {input_json_path}...")
    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Successfully loaded {len(data)} records")
    except Exception as e:
        print(f"❌ Error: Failed to read JSON file: {e}")
        return False
    
    # Generate dev_gold.sql
    print(f"📝 Generating {output_sql_path}...")
    try:
        with open(output_sql_path, 'w', encoding='utf-8') as f:
            for item in data:
                sql = item.get('SQL', '')
                db_id = item.get('db_id', '')
                
                # Write in format: SQL\tDB_ID
                f.write(f"{sql}\t{db_id}\n")
        
        print(f"✅ Successfully generated {output_sql_path}")
        print(f"📊 Total records: {len(data)}")
        return True
    except Exception as e:
        print(f"❌ Error: Failed to write SQL file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate dev_gold.sql from dev.json')
    parser.add_argument('--input', '-i', type=str, 
                        default='./data/dev.json',
                        help='Input dev.json file path (default: ./data/dev.json)')
    parser.add_argument('--output', '-o', type=str,
                        default='./data/dev_gold.sql',
                        help='Output dev_gold.sql file path (default: ./data/dev_gold.sql)')
    
    args = parser.parse_args()
    
    # Convert relative paths to absolute if needed
    if not os.path.isabs(args.input):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.input = os.path.join(script_dir, args.input)
    
    if not os.path.isabs(args.output):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.output = os.path.join(script_dir, args.output)
    
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"❌ Error: Input file not found: {args.input}")
        return
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"📁 Created output directory: {output_dir}")
    
    # Generate the file
    success = generate_dev_gold(args.input, args.output)
    
    if success:
        print("\n✨ Done! You can now run evaluation using:")
        print(f"   sh ./run/run_evaluation.sh")
    else:
        print("\n❌ Failed to generate dev_gold.sql")


if __name__ == '__main__':
    main()

