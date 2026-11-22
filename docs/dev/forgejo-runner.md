# Forgejo runner: on hold

**There is no self-hosted CI runner during 0.x (cabledrawer 17 Oct).** Running untrusted build code on the homelab needs more isolation than it's worth for a one-person project. CI starts at 1.0 on GitHub Actions, when the code moves to GitHub.

Until then:

- Before every pull request, `./check` at the repo root runs everything CI would have run, and its summary goes into the PR description.
- cabledrawer builds and pushes test images himself: see [test-on-homelab.md](test-on-homelab.md).
