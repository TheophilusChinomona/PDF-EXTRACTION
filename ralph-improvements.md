# Ralph Agent Improvements & Troubleshooting

**Last Updated:** 2026-01-28

---

## Known Issues

### Issue #1: "No messages returned" Error - Context Overflow

**Error Message:**
```
Error: No messages returned
    at LFf (B:/~BUN/root/claude.exe:6174:78)
    at processTicksAndRejections (native:7:39)
This error originated either by throwing inside of an async function without a catch block,
or by rejecting a promise which was not handled with .catch().
The promise rejected with the reason:
Error: No messages returned
```

**Root Cause:**
- Ralph feeds `CLAUDE.md` to Claude Code CLI
- `CLAUDE.md` instructs Claude to read `progress.txt`
- As stories are completed, `progress.txt` grows with detailed logs
- Large `progress.txt` (616 lines, 36KB) consumes 70-80% of context window
- No room left for Claude to generate responses → "No messages returned" error

**When This Happens:**
- Typically after 15-20 completed user stories
- Progress file exceeds ~500 lines or 30KB
- Ralph loop exits with error instead of continuing to next story

**Symptoms:**
- Ralph completes a story successfully (commits code, updates prd.json)
- Next iteration immediately fails with "No messages returned"
- `prd.json` shows stories marked complete but more remain with `passes: false`

**Solution Applied (2026-01-28):**
1. Archived full progress log to `archive/2026-01-28-progress-backup/progress-full.txt`
2. Condensed `progress.txt` from 616 lines (36KB) to 60 lines (4KB) - 90% reduction
3. Kept only:
   - Codebase Patterns section (critical learnings)
   - High-level summary of completed stories
   - Status snapshot (tests passing, stories complete)
   - List of remaining stories
4. Ralph resumed successfully after this fix

---

## Prevention Options

### Option 1: Periodic Manual Archiving

**When:** Every 5-10 completed stories (or when progress.txt exceeds 300 lines)

**How:**
```bash
cd scripts/ralph

# Archive current progress
cp progress.txt archive/$(date +%Y-%m-%d)-progress-backup.txt

# Condense progress.txt manually
# Keep: Codebase Patterns, Summary of completed stories, Status, Next stories
# Remove: Detailed iteration logs (archived for reference)
```

**Pros:**
- Full control over what to keep/archive
- Can review progress before condensing
- Simple bash commands

**Cons:**
- Requires manual monitoring
- Need to remember to do it
- Risk of forgetting until error occurs

---

### Option 2: Automated Archive Script

**Implementation:** Add to `ralph.sh` before the iteration loop

```bash
# Add after line 80 (after progress file initialization)

# Auto-archive if progress file gets too large
if [ -f "$PROGRESS_FILE" ]; then
  LINE_COUNT=$(wc -l < "$PROGRESS_FILE")

  if [ "$LINE_COUNT" -gt 400 ]; then
    echo "Progress file has $LINE_COUNT lines - archiving and condensing..."

    # Archive full progress
    DATE=$(date +%Y-%m-%d-%H%M%S)
    ARCHIVE_FILE="$ARCHIVE_DIR/$DATE-progress-full.txt"
    mkdir -p "$ARCHIVE_DIR"
    cp "$PROGRESS_FILE" "$ARCHIVE_FILE"
    echo "Archived to: $ARCHIVE_FILE"

    # Extract just the Codebase Patterns section and create condensed version
    awk '
      /^## Codebase Patterns/,/^---$/ { print; next }
      /^## [0-9]{4}-[0-9]{2}-[0-9]{2}/ {
        if (!summary_started) {
          print "## Completed Stories Summary"
          print ""
          summary_started = 1
        }
        completed++
      }
      END {
        print "✅ Completed " completed " user stories"
        print ""
        print "**Full detailed logs archived at:** archive/'$DATE'-progress-full.txt"
        print ""
        print "---"
      }
    ' "$PROGRESS_FILE" > "$PROGRESS_FILE.tmp"

    # Add header
    cat > "$PROGRESS_FILE" <<EOF
# Ralph Progress Log

Started: $(head -3 "$ARCHIVE_FILE" | tail -1)
Project: PDF-Extraction (Hybrid Architecture)
Branch: ralph/hybrid-extraction-pipeline

---

EOF
    cat "$PROGRESS_FILE.tmp" >> "$PROGRESS_FILE"
    rm "$PROGRESS_FILE.tmp"

    echo "Progress file condensed from $LINE_COUNT lines to $(wc -l < $PROGRESS_FILE) lines"
  fi
fi
```

**Pros:**
- Fully automated - no manual intervention needed
- Triggers automatically at 400 line threshold
- Preserves full logs in archive
- Continues seamlessly

**Cons:**
- More complex script logic
- Awk command needs testing across platforms
- Less control over what's condensed

---

### Option 3: Minimalist Progress Updates

**Approach:** Change how progress is appended - use compact format instead of detailed logs

**Update CLAUDE.md instructions** (in `scripts/ralph/CLAUDE.md`):

Replace the progress report format section with:

```markdown
## Progress Report Format

APPEND to progress.txt (never replace, always append):

### Compact Format (Default):
```
## [Date/Time] - [Story ID]: ✅ Complete
- [One-line summary of what was implemented]
- Files: [file1, file2, file3]
- Tests: [X] passing
---
```

### Detailed Format (Only for Complex Stories):
Use detailed format ONLY when you discover important patterns or gotchas:
```
## [Date/Time] - [Story ID]: ✅ Complete
- [Summary]
- Files: [list]
- **Key Pattern Discovered:** [Add to Codebase Patterns section]
---
```

**Examples:**

Compact:
```
## 2026-01-28 10:00 - US-008: ✅ Complete
- Implemented hybrid extraction pipeline (OpenDataLoader + Gemini)
- Files: app/services/pdf_extractor.py, tests/test_pdf_extractor.py
- Tests: 9 passing
---
```

Detailed (when pattern discovered):
```
## 2026-01-28 11:00 - US-009: ✅ Complete
- Implemented Vision fallback for low-quality PDFs
- Files: app/services/pdf_extractor.py, tests/test_pdf_extractor.py
- Tests: 14 passing
- **Key Pattern:** Always use finally block with try/except for cleanup to silence failures
---
```
```

**Pros:**
- Prevents progress file from growing too large
- Focuses on essential information
- Patterns still get documented in dedicated section
- Simple to implement (just update CLAUDE.md)

**Cons:**
- Less detailed history (but full git log available)
- May miss some useful context
- Requires discipline to identify when detail is needed

---

## Recommended Approach

**Hybrid: Option 3 (Minimalist Updates) + Option 1 (Manual Archiving)**

1. **Update CLAUDE.md now** to use compact progress format (Option 3)
   - Prevents future bloat
   - Keeps progress.txt lean
   - Important patterns still documented

2. **Manual archive when needed** (Option 1)
   - Simple backup command when file grows
   - Only needed every 20-30 stories with compact format
   - Full control over archiving

3. **Consider Option 2 for fully autonomous setups**
   - If running Ralph unattended for 50+ stories
   - Adds safety net without monitoring

---

## Monitoring

**Check progress file size periodically:**
```bash
wc -l scripts/ralph/progress.txt
du -h scripts/ralph/progress.txt
```

**Warning thresholds:**
- **300 lines:** Consider archiving soon
- **400 lines:** Should archive to prevent issues
- **500+ lines:** High risk of context overflow

**Healthy state:**
- 50-150 lines for compact format
- 200-300 lines for detailed format

---

## Archive Structure

```
scripts/ralph/
├── CLAUDE.md
├── prd.json
├── progress.txt                    # Active (condensed)
├── ralph.sh
└── archive/
    ├── 2026-01-28-progress-backup/
    │   └── progress-full.txt       # Full detailed logs
    ├── 2026-01-29-checkpoint/
    │   ├── prd.json
    │   └── progress.txt
    └── ...
```

---

## Testing the Fix

After condensing progress.txt or updating format:

```bash
cd scripts/ralph

# Verify file size is reasonable
wc -l progress.txt  # Should be < 300 lines

# Verify Codebase Patterns section is intact
head -30 progress.txt | grep "Codebase Patterns"

# Resume Ralph
./ralph.sh --tool claude 10
```

Ralph should continue without "No messages returned" errors.

---

## Future Enhancements

**Idea 1: Progress Rotation**
- Automatically rotate progress logs every 20 stories
- Keep last 3 rotations, archive older ones
- Similar to log rotation in production systems

**Idea 2: Separate Pattern File**
- Keep Codebase Patterns in dedicated file: `patterns.md`
- Reference it from progress.txt
- Never grows - just gets updated/refined

**Idea 3: Progress Database**
- Store progress in SQLite instead of text file
- Query recent progress for context
- Archive older entries automatically
- More complex but scales infinitely

---

## Related Files

- **CLAUDE.md:** Ralph agent instructions (update progress format here)
- **ralph.sh:** Main execution script (add auto-archive logic here)
- **progress.txt:** Active progress log (keep < 300 lines)
- **prd.json:** User story tracking (not affected by this issue)

---

**Document Version:** 1.0
**Last Issue Encountered:** 2026-01-28 (Context overflow at US-019/28)
**Resolution:** Archived and condensed progress.txt (616 → 60 lines)
