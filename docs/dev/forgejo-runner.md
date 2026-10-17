# Forgejo runner: on hold

**There is no self-hosted CI runner during 0.x (cabledrawer 17 Oct).** Running untrusted build code on the homelab needs more isolation than it's worth for a one-person project. CI starts at 1.0 on GitHub Actions, when the code moves to GitHub.

Until then:

- Before every pull request, `./check` at the repo root runs everything CI would have run, and its summary goes into the PR description.
- cabledrawer builds and pushes test images himself: see [test-on-homelab.md](test-on-homelab.md).

The full runner guide (a KVM VM on the NAS, the Authelia rules, and why Forgejo 16.0.6's automatic job token can't push images) is kept for reference:

- on the branch `m0.1/runner-guide` (pull request 6)
- in `main`'s history, at commit `8d27ddf` ("Runner guide: make the NAS VM the main path")

Don't set up a runner from it without a new decision from cabledrawer.
