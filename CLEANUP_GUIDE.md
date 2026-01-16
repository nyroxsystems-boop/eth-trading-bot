# Cleanup Script - Remove Backup Files

## Identified Backup Files: 85

This script will help clean up backup files from the codebase.

### Backup File Patterns

The following backup files were identified:
- `*.bak` files
- `*.bak.YYYY-MM-DD_HHMMSS` timestamped backups
- Various versioned backups

### Safe Cleanup Commands

```bash
# Preview what will be deleted (DRY RUN)
find . -name "*.bak*" -type f

# Count backup files
find . -name "*.bak*" -type f | wc -l

# Delete all .bak files (CAUTION!)
find . -name "*.bak*" -type f -delete

# Or delete selectively by date
find . -name "*.bak.2025-10-*" -type f -delete
```

### Recommended Approach

1. **Review first:**
   ```bash
   find . -name "*.bak*" -type f | sort
   ```

2. **Keep recent backups (last 7 days):**
   ```bash
   # Delete backups older than 7 days
   find . -name "*.bak*" -type f -mtime +7 -delete
   ```

3. **Or delete all except most recent:**
   ```bash
   # Keep only the most recent backup of each file
   # (Manual review recommended)
   ```

### Files to Keep

- `.env.example` - Template file
- `requirements.txt` - Current dependencies
- All files in `src/` - New modular code
- All files in `tests/` - Test suite

### Files Safe to Delete

All `*.bak*` files can be safely deleted as:
- Original files are in git
- New modular architecture replaces old code
- Backups are redundant with version control

## Execution

```bash
# Navigate to project root
cd /Users/xaaronvx/Desktop/ethbot_code

# Review files to be deleted
find . -name "*.bak*" -type f | head -20

# Execute cleanup
find . -name "*.bak*" -type f -delete

# Verify cleanup
find . -name "*.bak*" -type f | wc -l  # Should return 0
```

## Post-Cleanup

After cleanup, commit changes:
```bash
git add -A
git commit -m "chore: remove 85 backup files, complete modular refactoring"
```
