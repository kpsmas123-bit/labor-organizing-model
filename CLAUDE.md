## GIT WORKFLOW — ALL AGENTS MUST FOLLOW

At the end of every session, before stopping:
1. git push origin HEAD
2. Report your branch name to Sam
3. Sam merges via GitHub browser — do not attempt to merge to main yourself

Never work assuming files from other branches exist locally.
Always push your branch. Never merge other branches yourself.

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
