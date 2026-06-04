# Contributor Covenant Code of Conduct

## Our Pledge

We as contributors and maintainers of the SUDARSHAN UAV project pledge to make participation a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity and expression, level of experience, nationality, personal appearance, race, religion, or sexual identity and orientation.

We pledge to act and interact in ways that contribute to an open, welcoming, diverse, inclusive, and healthy community.

## Our Standards

**Examples of behaviour that contributes to a positive environment:**

- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experience levels
- Gracefully accepting constructive criticism
- Focusing on what is best for the project and the safety of those around it
- Showing empathy towards other community members
- Giving credit where it is due

**Examples of unacceptable behaviour:**

- Harassment, trolling, or derogatory comments
- Publishing others' private information without permission
- Submitting code that is intentionally unsafe, misleading, or designed to harm hardware or persons
- Personal or political attacks
- Any conduct that would be inappropriate in a professional setting

## Hardware Safety Addendum

This project controls physical hardware — a flying drone — capable of causing injury or damage. All contributors agree to the following additional standards:

1. **No code that endangers people or hardware.** Pull requests that weaken safety systems (DMS, ARM interlocks, ESC limits, PID output clamps) will be rejected regardless of technical merit, unless accompanied by a thorough safety analysis and sign-off from the project director.

2. **Test before you merge.** Any firmware change touching the FC control loop, motor mixing, or ESC communication must be bench-tested with propellers removed before a PR is opened. The PR description must include bench test results.

3. **Report safety hazards immediately.** If you discover a bug that could cause loss of control, fire, or injury, open a private issue tagged `[SAFETY]` rather than a public one. Do not exploit it.

4. **Props-off rule.** Any code that spins motors (MOTOR_TEST, CAL_ESC, SPIN_CH) must include clear documentation that propellers must be removed. Never add commands that bypass this requirement.

5. **The project director (Sudarshan) has final authority** on all safety-related decisions. Technical disagreements about non-safety matters are resolved by consensus; safety matters are not up for vote.

## Enforcement Responsibilities

The project maintainer (Sudarshan) is responsible for clarifying and enforcing the standards of acceptable behaviour and will take appropriate and fair corrective action in response to any behaviour that is deemed inappropriate, threatening, offensive, or harmful.

## Scope

This Code of Conduct applies within all project spaces — GitHub issues, pull requests, code comments, and any other forum used by this community — and also applies when an individual is officially representing the project in public spaces.

## Enforcement

Instances of abusive, harassing, unsafe, or otherwise unacceptable behaviour may be reported by opening a GitHub issue with the label `[CONDUCT]`. All complaints will be reviewed and investigated promptly and fairly.

**For safety-critical reports** (code that could cause physical harm): contact the project director directly via private GitHub issue. Do not post publicly until a fix has been prepared.

## Consequences

**1. Correction** — Private written warning with clarity about the violation and expected behaviour.

**2. Warning** — A warning with consequences for continued behaviour. No interaction with the people involved for a specified period.

**3. Temporary Ban** — A temporary ban from any interaction or contribution for a specified period.

**4. Permanent Ban** — Permanent removal from the project for repeated violations, harassment, or deliberate submission of unsafe code.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant](https://www.contributor-covenant.org), version 2.1, with the Hardware Safety Addendum specific to the SUDARSHAN UAV project.
