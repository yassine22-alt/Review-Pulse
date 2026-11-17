# Secrets audit

The supplied Gemini key appears in the original chat and its local conversation
record. Treat it as exposed and rotate it. The temporary launcher previously
retrieved that supplied value from the conversation record. That lookup has
been removed. Launchers now require an environment variable.

The audit found no matching provider credential in the scanned working files
or reachable Git history. It cannot certify every possible secret format.
The scanner never prints candidate values. The
[audit artifact](../reports/secrets-audit.json) records locations and SHA-256
fingerprints.

## Search scope

- 597 working text files, including tracked files, untracked files visible to
  Git, ignored reports, accessible run outputs and the temporary experiment
  launchers.
- Every blob reachable from all local refs and reflogs, streamed without a
  size cutoff. This covered 776 blobs, 286 trees and 37 commits.
- This chat's local conversation record, searched for the same patterns.
- Google AI Studio key prefixes, common hosted provider prefixes, GitHub
  tokens, AWS access identifiers and long bearer credentials.

The two conversation findings were the supplied Gemini key and an expired
temporary AWS access identifier in a research PDF's presigned URL from an
earlier browser tool response. The URL was dated 18 June 2026 with a 24-hour
lifetime. It belongs to the publisher's download infrastructure. No matching
AWS identifier was found in the project or Git history.

The scan excluded installed environments, dependency caches, ignored raw
datasets, working binary media and model files, and working files over 25 MB.
Binary blobs in reachable Git history were included. Eighty-five working
binary files were excluded. Nineteen old pytest run directories were
inaccessible under Windows permissions. A missing logs directory also appears
in the artifact's access diagnostics. Their contents are unverified.

No new provider key was written into a command, report or committed artifact.
The original key remains in conversation history. No remote history was
rewritten and no conversation record was deleted.

## Credential behavior

Hosted configuration ignores API keys, tokens and client secrets in `.env`
files. Non-secret model and provider settings can still be loaded there.
Environment mappings remain injectable in tests. Provider errors redact the
configured key before retaining an error message.

The security configuration and provider-client tests passed 17/17. Tests
cover an ignored file credential and redaction outside authentication errors.
No Gemini API key is currently present in the process environment. The live
hosted batch will wait for a rotated `GEMINI_API_KEY` supplied there.
