# Spec 20: Docker image for the terminal chat

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** a Dockerfile and a CI job that builds it and runs a smoke test
**Depends on:** 09, 18
**Delivery:** autonomous (after its dependencies)

---

## Summary

Running the agent needs Python 3.11 or newer, a virtual environment and an install. A Docker image
lets anyone run the chat with one command, on any machine, without touching their Python. The image
is for the terminal chat and the other commands; the web page is not exposed from the container,
because the server listens on the loopback address only (a decision of spec 12 that this spec does not
weaken).

## Context

The image installs the project in editable mode from /app, so the manual and the CSV files in /app/data
are found the same way as in a normal checkout. The database lives in a volume at /data, so the
conversations and the tickets survive the container. The API key is never part of the image: it is
passed at run time, and the build context excludes the .env file.

---

## Allowed files

**Production:** Dockerfile, .dockerignore (new); .github/workflows/ci.yml (a docker job)

**Tests:** tests/test_docker.py (new)

**Docs:** README.md, PROJECT_MAP.md

**Do not touch:** the source code and the web server.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| 🟡 RF-01 | The image installs the project with its data and starts the emporio command; with no argument it opens the chat | Must | Static check of the entrypoint and of the default command |
| 🟡 RF-02 | The database path points to a volume (/data) and the process runs as a user that is not root | Must | Static check |
| 🟡 RF-03 | The key and the local files are never in the image: the build context excludes .env, var, .git and the virtual environment, and no key is set in the file | Must | Static check of .dockerignore and of the Dockerfile |
| 🟡 RF-04 | The CI builds the image and runs two commands that need no key (data-report and stats) as a smoke test | Must | Static check of the workflow; the real proof is the run on GitHub |

## Non-functional requirements

- Only the official slim Python base image; no extra package installed in the image.

## Out of scope

- Publishing the image, a compose file and serving the web page from the container.

## Test checklist

- [ ] ✅ Dockerfile and .dockerignore checks
- [ ] ✅ The docker job of the workflow
- [ ] ✅ The job is green on GitHub (checked after the push)
