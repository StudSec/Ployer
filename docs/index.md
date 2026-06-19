# Ployer

[![Release](https://img.shields.io/github/v/release/StudSec/Ployer)](https://img.shields.io/github/v/release/StudSec/Ployer)
[![Build status](https://img.shields.io/github/actions/workflow/status/StudSec/Ployer/main.yml?branch=main)](https://github.com/StudSec/Ployer/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/StudSec/Ployer)](https://img.shields.io/github/commit-activity/m/StudSec/Ployer)
[![License](https://img.shields.io/github/license/StudSec/Ployer)](https://img.shields.io/github/license/StudSec/Ployer)

CTF Challenge deployment tool for our [custom challenge format](https://studsec.github.io/Challenges-Examples/)

## Quick Start

To install Ployer, you can use uv:

```bash
uv sync
# or
uv pip install ployer
```

You will need to set your docker context to the host where you want to deploy your challenges. See the
[docker documentation](https://docs.docker.com/engine/context/working-with-contexts/) for more information on how to do
this. Additionally, if pushing to a private registry, you will need to ensure that you are logged in to the registry
using `docker login`.

Then, you can use the `ployer` command to deploy your challenges:

```bash
# To deploy all challenges to a swarm cluster and add them to a CTFd instance with static scoring.
ployer --run --host challs.example.com --registry registry.ctfd.example.com --type static --runner swarm \
    --ctfd "https://ctfd.example.com ctfd_APIKEYTHATSLONG"

# To deploy all challenges with 'test' in their name as a regular docker container
ployer --run "1" --host challs.example.com --runner docker

# To stop all challenges on a swarm cluster
ployer --stop --host challs.example.com --runner swarm
```

> **NOTE:** if a challenge has `instanced = true`, then it will (currently) require the connected docker host to be a
swarm cluster.
