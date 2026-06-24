#!/usr/bin/env python3
"""
JSON to HTML Converter
Convert BIRD prediction result JSON files to beautiful HTML tables
"""

import json
import argparse
import os
from html import escape


def parse_sql_entry(entry):
    """
    Parse SQL entry, separate SQL query and database ID
    Format: "SQL\t----- bird -----\tdb_id"
    Also applies basic SQL format fixes
    """
    if '\t----- bird -----\t' in entry:
        parts = entry.split('\t----- bird -----\t')
        sql = parts[0].strip()
        db_id = parts[1].strip() if len(parts) > 1 else 'unknown'
        
        # Apply basic SQL format fixes (in case the JSON file wasn't fixed)
        sql = fix_sql_format_basic(sql)
        
        return sql, db_id
    return entry, 'unknown'


def fix_sql_format_basic(sql):
    """
    Apply basic SQL format fixes
    """
    import re
    # Fix SELECT followed by uppercase (SELECTMAX -> SELECT MAX)
    sql = re.sub(r'SELECT([A-Z][A-Z]+)', r'SELECT \1', sql)
    # Fix SELECT followed by lowercase (SELECTschools -> SELECT schools)
    sql = re.sub(r'SELECT([a-z])', r'SELECT \1', sql)
    # Fix multiple spaces
    sql = re.sub(r' +', ' ', sql)
    return sql.strip()


def generate_eval_results_html(eval_results):
    """
    Generate HTML for evaluation results
    """
    if not eval_results:
        return ""
    
    html = '<div class="eval-results">'
    html += '<h2>Evaluation Results</h2>'
    
    # Execution Accuracy (EX)
    if 'ex' in eval_results:
        ex = eval_results['ex']
        html += '<h3>Execution Accuracy (EX)</h3>'
        html += '<table class="eval-table">'
        html += '<thead><tr><th>Difficulty</th><th>Count</th><th>Accuracy (%)</th></tr></thead>'
        html += '<tbody>'
        
        for level in ['simple', 'moderate', 'challenging', 'total']:
            if level in ex:
                count = ex[level].get('count', 0)
                acc = ex[level].get('accuracy', 0)
                score_class = 'score-good' if acc >= 50 else ('score-medium' if acc >= 30 else 'score-low')
                html += f'<tr><td>{level.capitalize()}</td><td>{count}</td><td class="{score_class}">{acc:.2f}%</td></tr>'
        
        html += '</tbody></table>'
    
    # Valid Efficiency Score (VES)
    if 'ves' in eval_results:
        ves = eval_results['ves']
        html += '<h3 style="margin-top: 20px;">Valid Efficiency Score (VES)</h3>'
        html += '<table class="eval-table">'
        html += '<thead><tr><th>Difficulty</th><th>Count</th><th>VES Score</th></tr></thead>'
        html += '<tbody>'
        
        for level in ['simple', 'moderate', 'challenging', 'total']:
            if level in ves:
                count = ves[level].get('count', 0)
                score = ves[level].get('ves', 0)
                score_class = 'score-good' if score >= 50 else ('score-medium' if score >= 30 else 'score-low')
                html += f'<tr><td>{level.capitalize()}</td><td>{count}</td><td class="{score_class}">{score:.2f}</td></tr>'
        
        html += '</tbody></table>'
    
    html += '</div>'
    return html


def format_sql(sql):
    """
    Format SQL with syntax highlighting (simple version)
    """
    # Simple SQL keyword highlighting
    keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 
                'OUTER', 'ON', 'GROUP', 'BY', 'ORDER', 'LIMIT', 'HAVING', 
                'UNION', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 
                'DROP', 'AS', 'AND', 'OR', 'NOT', 'IN', 'EXISTS', 'COUNT', 
                'SUM', 'AVG', 'MAX', 'MIN', 'DISTINCT']
    
    sql_lower = sql.lower()
    formatted = sql
    
    for keyword in keywords:
        # Replace keywords (case-insensitive)
        pattern = r'\b' + keyword + r'\b'
        import re
        formatted = re.sub(pattern, f'<span class="keyword">{keyword.upper()}</span>', 
                          formatted, flags=re.IGNORECASE)
    
    return formatted


def generate_html(json_data, output_path, title="BIRD SQL Predictions", questions_data=None, eval_results=None):
    """
    Generate HTML file
    """
    # Calculate database count
    db_count = len(set(parse_sql_entry(v)[1] for v in json_data.values()))
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .stats {{
            display: flex;
            justify-content: space-around;
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .stat-item {{
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        
        .stat-label {{
            color: #6c757d;
            margin-top: 5px;
        }}
        
        .table-container {{
            overflow-x: auto;
            padding: 20px;
        }}
        
        .sql-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        
        .sql-item {{
            margin-bottom: 10px;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            background: white;
            overflow: hidden;
            display: none; /* Hidden by default, shown by pagination */
        }}
        
        .sql-item-header {{
            padding: 15px;
            background: #f8f9fa;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }}
        
        .sql-item-header:hover {{
            background: #e9ecef;
        }}
        
        .sql-item-header.active {{
            background: #667eea;
            color: white;
        }}
        
        .sql-item-info {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        
        .sql-item-index {{
            font-weight: bold;
            color: #667eea;
            min-width: 60px;
        }}
        
        .sql-item-header.active .sql-item-index {{
            color: white;
        }}
        
        .sql-item-question {{
            flex: 1;
            font-size: 0.95em;
            color: #333;
        }}
        
        .sql-item-header.active .sql-item-question {{
            color: white;
        }}
        
        .sql-item-db {{
            background: #e7f3ff;
            color: #0066cc;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: 600;
            font-size: 0.85em;
        }}
        
        .sql-item-header.active .sql-item-db {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
        }}
        
        .sql-item-toggle {{
            font-size: 1.2em;
            transition: transform 0.3s;
            color: #667eea;
        }}
        
        .sql-item-header.active .sql-item-toggle {{
            color: white;
            transform: rotate(90deg);
        }}
        
        .sql-item-content {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }}
        
        .sql-item-content.expanded {{
            max-height: 2000px;
            transition: max-height 0.5s ease-in;
        }}
        
        .sql-item-details {{
            padding: 15px;
            border-top: 1px solid #e9ecef;
        }}
        
        .sql-item-details-row {{
            margin-bottom: 15px;
        }}
        
        .sql-item-details-row:last-child {{
            margin-bottom: 0;
        }}
        
        .sql-item-label {{
            font-weight: 600;
            color: #667eea;
            margin-bottom: 5px;
            font-size: 0.9em;
        }}
        
        .pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin: 30px 0;
            padding: 20px;
        }}
        
        .pagination-info {{
            color: #6c757d;
            margin: 0 20px;
        }}
        
        .pagination-button {{
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.2s;
        }}
        
        .pagination-button:hover {{
            background: #764ba2;
        }}
        
        .pagination-button:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}
        
        .pagination-button.active {{
            background: #764ba2;
            font-weight: bold;
        }}
        
        .page-numbers {{
            display: flex;
            gap: 5px;
        }}
        
        .page-number {{
            padding: 8px 12px;
            background: #f8f9fa;
            color: #667eea;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.2s;
        }}
        
        .page-number:hover {{
            background: #667eea;
            color: white;
        }}
        
        .page-number.active {{
            background: #667eea;
            color: white;
            font-weight: bold;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            table-layout: fixed;
        }}
        
        thead {{
            background: #667eea;
            color: white;
        }}
        
        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            border-bottom: 3px solid #764ba2;
        }}
        
        th.index {{
            width: 80px;
        }}
        
        th:nth-child(2) {{
            width: 25%;
        }}
        
        th:nth-child(3) {{
            width: 50%;
        }}
        
        th:nth-child(4) {{
            width: 15%;
        }}
        
        td {{
            padding: 15px;
            border-bottom: 1px solid #e9ecef;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .index {{
            font-weight: bold;
            color: #667eea;
            text-align: center;
            width: 80px;
        }}
        
        .question {{
            font-size: 1em;
            color: #333;
            margin-bottom: 8px;
            line-height: 1.5;
        }}
        
        .evidence {{
            font-size: 0.85em;
            color: #666;
            margin-top: 8px;
            padding: 8px;
            background: #fff3cd;
            border-left: 3px solid #ffc107;
            border-radius: 3px;
        }}
        
        .evidence strong {{
            color: #856404;
        }}
        
        .sql {{
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        
        .sql .keyword {{
            color: #d63384;
            font-weight: bold;
        }}
        
        .db-id {{
            background: #e7f3ff;
            color: #0066cc;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: 600;
            display: inline-block;
        }}
        
        .footer {{
            text-align: center;
            padding: 20px;
            color: #6c757d;
            background: #f8f9fa;
        }}
        
        .eval-results {{
            margin: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            border: 2px solid #667eea;
        }}
        
        .eval-results h2 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.5em;
        }}
        
        .eval-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        
        .eval-table th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: center;
        }}
        
        .eval-table td {{
            padding: 10px;
            text-align: center;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .eval-table tr:hover {{
            background: #f0f0f0;
        }}
        
        .score-good {{
            color: #28a745;
            font-weight: bold;
        }}
        
        .score-medium {{
            color: #ffc107;
            font-weight: bold;
        }}
        
        .score-low {{
            color: #dc3545;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>BIRD SQL Prediction Results Visualization</p>
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-value">{len(json_data)}</div>
                <div class="stat-label">Total Records</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{db_count}</div>
                <div class="stat-label">Number of Databases</div>
            </div>
        </div>
        
        {generate_eval_results_html(eval_results)}
        
        <div class="table-container">
            <ul class="sql-list" id="sql-list">
"""
    
    # Add collapsible list items
    all_items_html = ""
    for index, sql_entry in sorted(json_data.items(), key=lambda x: int(x[0])):
        sql, db_id = parse_sql_entry(sql_entry)
        sql_escaped = escape(sql)
        sql_formatted = format_sql(sql_escaped)
        
        # Get question/prompt if available
        question_text = ""
        evidence_text = ""
        if questions_data and index in questions_data:
            q_data = questions_data[index]
            question_text = q_data.get('question', '')
            evidence_text = q_data.get('evidence', '')
        
        # Truncate question for header if too long
        question_display = question_text if question_text else "Question not available"
        if len(question_display) > 100:
            question_display = question_display[:100] + "..."
        
        all_items_html += f"""
                <li class="sql-item" data-index="{index}">
                    <div class="sql-item-header" onclick="toggleSqlItem(this)">
                        <div class="sql-item-info">
                            <span class="sql-item-index">#{index}</span>
                            <span class="sql-item-question">{escape(question_display)}</span>
                            <span class="sql-item-db">{escape(db_id)}</span>
                        </div>
                        <span class="sql-item-toggle">▶</span>
                    </div>
                    <div class="sql-item-content">
                        <div class="sql-item-details">
"""
        
        # Add question if available
        if question_text:
            all_items_html += f"""
                            <div class="sql-item-details-row">
                                <div class="sql-item-label">Question:</div>
                                <div class="question">{escape(question_text)}</div>
                            </div>
"""
        
        # Add evidence if available
        if evidence_text:
            all_items_html += f"""
                            <div class="sql-item-details-row">
                                <div class="sql-item-label">External Knowledge:</div>
                                <div class="evidence"><strong>External Knowledge:</strong> {escape(evidence_text)}</div>
                            </div>
"""
        
        # Add SQL query
        all_items_html += f"""
                            <div class="sql-item-details-row">
                                <div class="sql-item-label">SQL Query:</div>
                                <div class="sql">{sql_formatted}</div>
                            </div>
                        </div>
                    </div>
                </li>
"""
    
    # Add all items to HTML
    html_content += all_items_html
    
    # Calculate pagination
    total_items = len(json_data)
    items_per_page = 20
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    # Generate pagination HTML
    pagination_html = f"""
            </ul>
            
            <div class="pagination" id="pagination">
                <button class="pagination-button" id="prev-btn" onclick="changePage(currentPage - 1)">Previous</button>
                <div class="page-numbers" id="page-numbers"></div>
                <button class="pagination-button" id="next-btn" onclick="changePage(currentPage + 1)">Next</button>
                <div class="pagination-info">
                    <span id="page-info">Page 1 of {total_pages}</span>
                    <span style="margin-left: 20px;">({total_items} total items)</span>
                </div>
            </div>
        </div>
"""
    
    html_content += pagination_html
    
    html_content += f"""
        <script>
            const itemsPerPage = 20;
            let currentPage = 1;
            const totalItems = {total_items};
            const totalPages = Math.ceil(totalItems / itemsPerPage);
            
            function toggleSqlItem(header) {{
                const item = header.parentElement;
                const content = item.querySelector('.sql-item-content');
                const isExpanded = content.classList.contains('expanded');
                
                if (isExpanded) {{
                    content.classList.remove('expanded');
                    header.classList.remove('active');
                }} else {{
                    content.classList.add('expanded');
                    header.classList.add('active');
                }}
            }}
            
            function showPage(page) {{
                const items = document.querySelectorAll('.sql-item');
                const startIndex = (page - 1) * itemsPerPage;
                const endIndex = Math.min(startIndex + itemsPerPage, totalItems);
                
                // Hide all items first
                items.forEach((item) => {{
                    item.style.display = 'none';
                }});
                
                // Show items for current page
                items.forEach((item, index) => {{
                    if (index >= startIndex && index < endIndex) {{
                        item.style.display = 'block';
                    }}
                }});
                
                updatePagination(page);
            }}
            
            function updatePagination(page) {{
                currentPage = page;
                
                // Update prev/next buttons
                document.getElementById('prev-btn').disabled = (page === 1);
                document.getElementById('next-btn').disabled = (page === totalPages);
                
                // Update page info
                document.getElementById('page-info').textContent = `Page ${{page}} of ${{totalPages}}`;
                
                // Update page numbers
                const pageNumbers = document.getElementById('page-numbers');
                pageNumbers.innerHTML = '';
                
                // Show page numbers (max 10 visible)
                let startPage = Math.max(1, page - 4);
                let endPage = Math.min(totalPages, page + 5);
                
                if (startPage > 1) {{
                    const firstBtn = document.createElement('button');
                    firstBtn.className = 'page-number';
                    firstBtn.textContent = '1';
                    firstBtn.onclick = () => changePage(1);
                    pageNumbers.appendChild(firstBtn);
                    if (startPage > 2) {{
                        const ellipsis = document.createElement('span');
                        ellipsis.textContent = '...';
                        ellipsis.style.padding = '8px';
                        pageNumbers.appendChild(ellipsis);
                    }}
                }}
                
                for (let i = startPage; i <= endPage; i++) {{
                    const btn = document.createElement('button');
                    btn.className = 'page-number' + (i === page ? ' active' : '');
                    btn.textContent = i;
                    btn.onclick = () => changePage(i);
                    pageNumbers.appendChild(btn);
                }}
                
                if (endPage < totalPages) {{
                    if (endPage < totalPages - 1) {{
                        const ellipsis = document.createElement('span');
                        ellipsis.textContent = '...';
                        ellipsis.style.padding = '8px';
                        pageNumbers.appendChild(ellipsis);
                    }}
                    const lastBtn = document.createElement('button');
                    lastBtn.className = 'page-number';
                    lastBtn.textContent = totalPages;
                    lastBtn.onclick = () => changePage(totalPages);
                    pageNumbers.appendChild(lastBtn);
                }}
            }}
            
            function changePage(page) {{
                if (page < 1 || page > totalPages) return;
                showPage(page);
                // Keep current scroll position instead of scrolling to top
            }}
            
            // Make changePage globally accessible
            window.changePage = changePage;
            
            // Initialize - run immediately and also on DOMContentLoaded
            function initialize() {{
                showPage(1);
                
                // Add keyboard support for SQL items
                const headers = document.querySelectorAll('.sql-item-header');
                headers.forEach(header => {{
                    header.setAttribute('tabindex', '0');
                    header.addEventListener('keypress', function(e) {{
                        if (e.key === 'Enter' || e.key === ' ') {{
                            e.preventDefault();
                            toggleSqlItem(this);
                        }}
                    }});
                }});
            }}
            
            // Run immediately if DOM is ready, otherwise wait
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initialize);
            }} else {{
                initialize();
            }}
        </script>
        
        <div class="footer">
            <p>Generated by JSON to HTML Converter</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML file generated: {output_path}")
    print(f"📊 Processed {len(json_data)} records")


def load_questions_data(questions_file):
    """
    Load questions from original dev.json file
    Returns a dictionary mapping index to question data
    """
    if not questions_file or not os.path.exists(questions_file):
        return None
    
    try:
        with open(questions_file, 'r', encoding='utf-8') as f:
            questions_list = json.load(f)
        
        # Convert list to dict with question_id as key
        questions_dict = {}
        for item in questions_list:
            q_id = str(item.get('question_id', ''))
            questions_dict[q_id] = {
                'question': item.get('question', ''),
                'evidence': item.get('evidence', ''),
                'db_id': item.get('db_id', '')
            }
        
        return questions_dict
    except Exception as e:
        print(f"⚠️  Warning: Failed to load questions file: {e}")
        return None


def load_eval_results(eval_file):
    """
    Load evaluation results from JSON file
    Expected format:
    {
        "ex": {
            "simple": {"count": 925, "accuracy": 51.46},
            "moderate": {"count": 464, "accuracy": 29.96},
            "challenging": {"count": 145, "accuracy": 20.00},
            "total": {"count": 1534, "accuracy": 41.98}
        },
        "ves": {
            "simple": {"count": 925, "ves": 62.10},
            "moderate": {"count": 464, "ves": 49.18},
            "challenging": {"count": 145, "ves": 20.82},
            "total": {"count": 1534, "ves": 54.29}
        }
    }
    """
    if not eval_file or not os.path.exists(eval_file):
        return None
    
    try:
        with open(eval_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        return results
    except Exception as e:
        print(f"⚠️  Warning: Failed to load evaluation results: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Convert JSON file to HTML table')
    parser.add_argument('--input', '-i', type=str, required=True,
                        help='Input JSON file path')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output HTML file path (default: input filename.html)')
    parser.add_argument('--title', '-t', type=str, default='BIRD SQL Predictions',
                        help='HTML page title')
    parser.add_argument('--questions', '-q', type=str, default=None,
                        help='Path to original dev.json file with questions (optional)')
    parser.add_argument('--eval-results', '-e', type=str, default=None,
                        help='Path to evaluation results JSON file (optional)')
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"❌ Error: File not found: {args.input}")
        return
    
    # Determine output file path
    if args.output is None:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        output_dir = os.path.dirname(args.input)
        args.output = os.path.join(output_dir, f"{base_name}.html")
    
    # Read JSON file
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        print(f"📖 Successfully read JSON file: {args.input}")
    except Exception as e:
        print(f"❌ Error: Failed to read JSON file: {e}")
        return
    
    # Load questions data if provided
    questions_data = None
    if args.questions:
        questions_data = load_questions_data(args.questions)
        if questions_data:
            print(f"📖 Successfully loaded questions from: {args.questions}")
        else:
            print(f"⚠️  Warning: Could not load questions, continuing without them")
    
    # Load evaluation results if provided
    eval_results = None
    if args.eval_results:
        eval_results = load_eval_results(args.eval_results)
        if eval_results:
            print(f"📊 Successfully loaded evaluation results from: {args.eval_results}")
        else:
            print(f"⚠️  Warning: Could not load evaluation results, continuing without them")
    
    # Generate HTML
    try:
        generate_html(json_data, args.output, args.title, questions_data, eval_results)
    except Exception as e:
        print(f"❌ Error: Failed to generate HTML: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

