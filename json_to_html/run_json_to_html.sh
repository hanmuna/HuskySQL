#!/bin/bash

# JSON to HTML Conversion Script
# Usage: ./run_json_to_html.sh [input JSON file] [output HTML file (optional)]

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_SCRIPT="${SCRIPT_DIR}/json_to_html.py"

# Default input file (if not specified)
DEFAULT_INPUT="../llm/exp_result/turbo_output_kg/predict_dev.json"

# Check parameters
if [ -z "$1" ]; then
    INPUT_FILE="${DEFAULT_INPUT}"
    echo "⚠️  No input file specified, using default: ${INPUT_FILE}"
else
    INPUT_FILE="$1"
fi

# Convert relative path to absolute path if needed
if [[ ! "$INPUT_FILE" = /* ]]; then
    INPUT_FILE="${SCRIPT_DIR}/${INPUT_FILE}"
fi

# Check if input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ Error: File not found: ${INPUT_FILE}"
    echo "💡 Tip: Please specify the correct JSON file path"
    exit 1
fi

# Determine output file path
if [ -z "$2" ]; then
    # Generate output filename from input filename
    BASE_NAME=$(basename "${INPUT_FILE}" .json)
    OUTPUT_DIR=$(dirname "${INPUT_FILE}")
    OUTPUT_FILE="${OUTPUT_DIR}/${BASE_NAME}.html"
else
    OUTPUT_FILE="$2"
    # Convert relative path to absolute path if needed
    if [[ ! "$OUTPUT_FILE" = /* ]]; then
        OUTPUT_FILE="${SCRIPT_DIR}/${OUTPUT_FILE}"
    fi
fi

# Create output directory if it doesn't exist
OUTPUT_DIR=$(dirname "${OUTPUT_FILE}")
mkdir -p "${OUTPUT_DIR}"

echo "🚀 Starting conversion..."
echo "📥 Input file: ${INPUT_FILE}"
echo "📤 Output file: ${OUTPUT_FILE}"
echo ""

# Try to find questions file automatically
QUESTIONS_FILE=""
if [ -f "../llm/data/dev.json" ]; then
    QUESTIONS_FILE="../llm/data/dev.json"
elif [ -f "../../llm/data/dev.json" ]; then
    QUESTIONS_FILE="../../llm/data/dev.json"
fi

# Try to find evaluation results file automatically
EVAL_RESULTS_FILE=""
# Check if eval_results.json exists in the same directory as input file
INPUT_DIR=$(dirname "${INPUT_FILE}")
if [ -f "${INPUT_DIR}/eval_results.json" ]; then
    EVAL_RESULTS_FILE="${INPUT_DIR}/eval_results.json"
elif [ -f "../llm/exp_result/turbo_output_kg/eval_results.json" ]; then
    EVAL_RESULTS_FILE="../llm/exp_result/turbo_output_kg/eval_results.json"
elif [ -f "../llm/exp_result/turbo_output/eval_results.json" ]; then
    EVAL_RESULTS_FILE="../llm/exp_result/turbo_output/eval_results.json"
fi

# Build command
if [ -n "${QUESTIONS_FILE}" ]; then
    echo "📋 Found questions file: ${QUESTIONS_FILE}"
else
    echo "⚠️  Questions file not found, generating HTML without questions"
fi

if [ -n "${EVAL_RESULTS_FILE}" ]; then
    echo "📊 Found evaluation results: ${EVAL_RESULTS_FILE}"
else
    echo "⚠️  Evaluation results not found, generating HTML without evaluation scores"
fi

# Run Python script
if [ -n "${QUESTIONS_FILE}" ] && [ -n "${EVAL_RESULTS_FILE}" ]; then
    python3 "${PYTHON_SCRIPT}" \
        --input "${INPUT_FILE}" \
        --output "${OUTPUT_FILE}" \
        --title "BIRD SQL Predictions" \
        --questions "${QUESTIONS_FILE}" \
        --eval-results "${EVAL_RESULTS_FILE}"
elif [ -n "${QUESTIONS_FILE}" ]; then
    python3 "${PYTHON_SCRIPT}" \
        --input "${INPUT_FILE}" \
        --output "${OUTPUT_FILE}" \
        --title "BIRD SQL Predictions" \
        --questions "${QUESTIONS_FILE}"
elif [ -n "${EVAL_RESULTS_FILE}" ]; then
    python3 "${PYTHON_SCRIPT}" \
        --input "${INPUT_FILE}" \
        --output "${OUTPUT_FILE}" \
        --title "BIRD SQL Predictions" \
        --eval-results "${EVAL_RESULTS_FILE}"
else
    python3 "${PYTHON_SCRIPT}" \
        --input "${INPUT_FILE}" \
        --output "${OUTPUT_FILE}" \
        --title "BIRD SQL Predictions"
fi

# Check if successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✨ Conversion completed!"
    echo "📂 HTML file location: ${OUTPUT_FILE}"
    echo ""
    echo "💡 Tip: Open the HTML file in your browser to view the results"
    
    # Try to open in default browser (macOS)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        read -p "Open in browser? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            open "${OUTPUT_FILE}"
        fi
    fi
else
    echo ""
    echo "❌ Conversion failed, please check the error messages"
    exit 1
fi

