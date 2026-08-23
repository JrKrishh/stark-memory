# Lessons Learned

A log of past mistakes and their fixes, maintained by the learn-from-mistakes skill.
Consult before non-trivial tasks; apply logged fixes when a known error recurs;
graduate recurring or high-severity lessons into automated guards.
Newest entries go at the top of their category.

## Build & Tooling

### [2026-08-22] `git checkout -B <branch> <ref>` silently discards unpushed commits
- **Severity:** medium
- **Trigger:** restarting or re-pointing a branch after its PR merged (`git checkout -B <branch> origin/main` / `FETCH_HEAD`)
- **What happened:** a just-made commit (a one-line fix) was not yet pushed when the branch was reset onto the freshly fetched main. `-B` moved the branch pointer, leaving the commit unreferenced and absent from the working tree — it looked like the edit had never been made.
- **Root cause:** `-B` force-resets an existing branch to the given ref with no check for commits that exist only on that branch; the commit survives only in the reflog.
- **Fix:** recovered it with `git reflog` (the commit is listed by its message) and `git cherry-pick <sha>` onto the reset branch, then pushed.
- **Prevention:** before `checkout -B` / `reset --hard` on a branch, run `git log --oneline @{upstream}..HEAD` (or `git status`) and push or stash anything it lists; if a commit does go missing, check `git reflog` before redoing the work by hand.
