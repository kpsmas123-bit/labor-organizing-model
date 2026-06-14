## GIT WORKFLOW

### Default: push directly to main

For most changes, commit and push directly to main:

git add -A
git commit -m "your message"
git push origin main

Do this for: data pipeline changes, scoring fixes, 
bug fixes, new scripts, workflow files, CSS token 
changes, content updates, test fixes.

### Branch + PR required (Sam reviews before merge)

Create a branch and PR — do NOT merge — for:

1. VISUAL CHANGES — any change to HTML layout structure,
   new CSS components, page redesigns, navigation changes
2. SCORING MODEL CHANGES — any change to config/weights.json,
   config/thresholds.json, or scoring/ module formulas
3. DATA FILE RENAMES OR RESTRUCTURING — renaming canonical
   data files, changing data schema

For branch + PR:
git checkout -b descriptive-branch-name
git add -A
git commit -m "your message"
git push origin HEAD

Then report the PR URL and stop. Sam merges via GitHub.

### Never do
- Force push
- Push to a branch that already has an open PR
  without being asked
- Merge your own PR
- Use GitHub API — standard git commands only

---

## PERMISSION PROMPT RULES

Before requesting ANY permission, you must first explain in plain language:
1. What you are about to do in one sentence
2. Why you need to do it
3. What the risk is if something goes wrong
4. A clear recommendation: SAFE TO ALLOW or DO NOT ALLOW

Format it like this every time:

---
PERMISSION REQUEST
What: [one sentence, no jargon]
Why: [one sentence]
Risk if allowed: [one sentence]
My recommendation: SAFE TO ALLOW / DO NOT ALLOW
---

Then show the permission prompt.

Never request permission to:
- Use API keys or credentials that are not in our .env file
- Access any URL containing: azure, internal, admin, backend, search.windows.net
- Query any government system's internal infrastructure
- Access any third party's database or backend system
- Write credentials to any tracked file

If you find credentials embedded in someone else's website JavaScript, 
stop immediately and tell Sam — do not attempt to use them.
