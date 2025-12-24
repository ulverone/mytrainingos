#!/bin/bash

# ============================================================================
# MyTrainingOS Launcher for macOS
# ============================================================================
# This script launches the Streamlit dashboard with a single double-click
# No need to open Terminal or type commands!
# ============================================================================

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script directory
cd "$SCRIPT_DIR"

echo "🏃 Starting MyTrainingOS..."
echo "📂 Working directory: $SCRIPT_DIR"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "✅ Found virtual environment, activating..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "✅ Found virtual environment, activating..."
    source .venv/bin/activate
else
    echo "⚠️  No virtual environment found, using system Python"
fi

# Check if Streamlit is installed
if ! command -v streamlit &> /dev/null; then
    echo "❌ Streamlit not found!"
    echo "Installing required packages..."
    pip install streamlit pandas numpy plotly
fi

# Launch Streamlit
echo "🚀 Launching MyTrainingOS dashboard..."
echo "💡 The browser will open automatically"
echo "🛑 To stop the server, close this window or press Ctrl+C"
echo ""

# Open browser after a short delay (in background)
(sleep 3 && open http://localhost:8501) &

# Run Streamlit (this will keep the terminal open)
streamlit run app.py --server.headless=true --browser.gatherUsageStats=false

# If Streamlit exits, pause before closing
echo ""
echo "✅ MyTrainingOS has been stopped"
read -p "Press Enter to close this window..."
