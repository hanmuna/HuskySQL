#!/usr/bin/env python3
"""
Fix SQL format issues in prediction JSON files
Fixes common issues like SELECTMAX -> SELECT MAX, SELECTschools -> SELECT schools
"""

import json
import re
import argparse
import os


def fix_sql_format(sql):
    """
    Fix common SQL format issues
    """
    # Remove markdown code blocks (```sql...```)
    sql = re.sub(r'```sql\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'```\s*', '', sql)
    
    # Fix duplicate SELECT (SELECT SELECT -> SELECT)
    sql = re.sub(r'SELECT\s+SELECT', 'SELECT', sql, flags=re.IGNORECASE)
    
    # Fix SELECT followed by uppercase (SELECTMAX -> SELECT MAX)
    sql = re.sub(r'SELECT([A-Z][A-Z]+)', r'SELECT \1', sql)
    
    # Fix SELECT followed by lowercase (SELECTschools -> SELECT schools)
    sql = re.sub(r'SELECT([a-z])', r'SELECT \1', sql)
    
    # Fix other common patterns
    sql = re.sub(r'FROM([A-Za-z])', r'FROM \1', sql)
    sql = re.sub(r'WHERE([A-Za-z])', r'WHERE \1', sql)
    sql = re.sub(r'JOIN([A-Za-z])', r'JOIN \1', sql)
    sql = re.sub(r'ORDER([A-Za-z])', r'ORDER \1', sql)
    sql = re.sub(r'GROUP([A-Za-z])', r'GROUP \1', sql)
    sql = re.sub(r'LIMIT([0-9])', r'LIMIT \1', sql)
    
    # Fix multiple spaces
    sql = re.sub(r' +', ' ', sql)
    
    return sql.strip()


def fix_json_file(input_path, output_path=None):
    """
    Fix SQL format in prediction JSON file
    """
    if output_path is None:
        output_path = input_path
    
    print(f"📖 Reading {input_path}...")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Successfully loaded {len(data)} records")
    except Exception as e:
        print(f"❌ Error: Failed to read JSON file: {e}")
        return False
    
    # Fix SQL format
    print(f"🔧 Fixing SQL format...")
    fixed_data = {}
    fixed_count = 0
    
    for key, value in data.items():
        if isinstance(value, str) and '\t----- bird -----\t' in value:
            sql, db_id = value.split('\t----- bird -----\t')
            original_sql = sql
            
            # Fix SQL format
            sql = fix_sql_format(sql)
            
            if sql != original_sql:
                fixed_count += 1
            
            fixed_data[key] = f"{sql}\t----- bird -----\t{db_id}"
        else:
            fixed_data[key] = value
    
    # Save fixed file
    print(f"💾 Saving to {output_path}...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(fixed_data, f, indent=4)
        
        print(f"✅ Successfully fixed {fixed_count} SQL statements")
        print(f"📊 Total records: {len(fixed_data)}")
        return True
    except Exception as e:
        print(f"❌ Error: Failed to write JSON file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Fix SQL format in prediction JSON files')
    parser.add_argument('--input', '-i', type=str, required=True,
                        help='Input JSON file path')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output JSON file path (default: overwrite input file)')
    parser.add_argument('--backup', '-b', action='store_true',
                        help='Create backup of original file')
    
    args = parser.parse_args()
    
    # Convert relative paths to absolute if needed
    if not os.path.isabs(args.input):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.input = os.path.join(script_dir, args.input)
    
    if args.output and not os.path.isabs(args.output):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.output = os.path.join(script_dir, args.output)
    
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"❌ Error: Input file not found: {args.input}")
        return
    
    # Create backup if requested
    if args.backup:
        backup_path = args.input + '.backup'
        print(f"📦 Creating backup: {backup_path}")
        import shutil
        shutil.copy2(args.input, backup_path)
    
    # Fix the file
    success = fix_json_file(args.input, args.output)
    
    if success:
        print("\n✨ Done! SQL format has been fixed.")
        print("💡 You can now re-run the evaluation:")
        print("   sh ./run/run_evaluation.sh")
    else:
        print("\n❌ Failed to fix SQL format")


if __name__ == '__main__':
    main()

