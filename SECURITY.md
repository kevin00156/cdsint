# Security Policy

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting: the
**Security** tab of this repository, then **Report a vulnerability**.

Say what an attacker can do with it, not only what looks wrong. One line that
reproduces the problem is worth more than a page of theory. You will get an
acknowledgement; if a fix ships, the changelog credits you under whatever name
you give, or nobody at all if you would rather.

## Which versions get fixes

There is no published release yet, so there is nothing to backport to. Fixes go
on `main`, and `main` is the only place to get them. When releases start, this
section will say which ones are still supported.

## What this tool can reach

Worth knowing before deciding whether something is a vulnerability here.

`cdsint` runs on your machine with your permissions, and its other half runs
inside the IDE as the IDE. Between them they read and write the whole PLC
project, write files wherever the project's sync folder points, start and stop
the IDE, and — when the project's settings allow it — connect to a controller
and download to it.

That last one is deliberately gated. A `plc` command is refused unless the
project's `.cdsint.json` settings file lists it, and the refusal is exit code 5.
Anything that makes `plc download` run against a project whose settings do not
allow it is a vulnerability. So is anything that makes an export or import write
outside the configured sync folder.

Feeding this tool a `.project`, `.st` or settings file from someone you do not
trust is not a supported use. It parses all three assuming they came from you.

## Not a vendor product

This is a third-party tool. It is not endorsed by CODESYS, Lenze or Delta, and
it drives their IDEs through the scripting API those IDEs publish. A script with
this much access to a project belongs to the person who read it first — review
it before you point it at a machine that is running.
