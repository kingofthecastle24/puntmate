#!/bin/bash
# PuntMate NZ — Round 19 Post Runner
# Double-click this file to post R19 picks to Telegram + commit to git

cd "$(dirname "$0")"
echo "📍 Working from: $(pwd)"
echo ""

# Post to Telegram
echo "📡 Posting to Telegram..."
python3 scripts/post_r19.py
echo ""

# Git commit and push
echo "📦 Committing to git..."
git add .
git commit -m "Round 19 picks — Storm banker + home treble multi"
git push
echo ""
echo "✅ All done!"
echo ""
echo "Press any key to close..."
read -n 1
