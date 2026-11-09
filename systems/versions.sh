#!/bin/bash
# shellcheck disable=SC2034 # settings: read by the scripts that source this file
# Where each source tree comes from. Sourced by systems/common.sh; don't run it.
#
# Third-party libraries are pinned to a tag AND the commit it pointed to when it was chosen: a tag
# can move, and the build refuses a checkout whose HEAD isn't the pinned commit. They're cloned
# under <prefix>/src, so each stack has its own copy.
#
# The stream-triggering repositories are NOT pinned here: they're working trees (the meta repo's
# repos/*, or clones under -g). The ref below is only what a fresh clone checks out, and the build
# warns when an existing checkout is on another branch. The manifest records the exact commit.

# Third party (chosen 2026-11-09)
SILO_URL=https://github.com/LLNL/Silo.git
SILO_REF=4.12.1
SILO_SHA=f05c5a8e6c22b784b7f5eb958d50218cae873d07

KOKKOS_URL=https://github.com/kokkos/kokkos.git
KOKKOS_REF=5.2.2
KOKKOS_SHA=8e15454876298832f013ebcaf08d53825b5bda40

# Only for aCG's rccl backend, and optional even there: RCCL runs without it, slowly.
OFI_NCCL_URL=https://github.com/aws/aws-ofi-nccl.git
OFI_NCCL_REF=v1.22.0
OFI_NCCL_SHA=80c6d32527bbf764dd06e87b05321b044da36220

# METIS isn't cloned: it comes from METIS_DIR (Spack on Tuolumne, see metis-spack.yaml; the metis
# module on Frontier, see frontier.modules).

# Stream-triggering repositories: <directory name under -g> <url> <ref for a fresh clone>
ST_REPO="stream-triggering https://github.com/mpi-advance/stream-triggering.git feat-header-align"
CABANA_REPO="Cabana https://github.com/CUP-ECS/Cabana.git mpi-advance-stream-halo"
CABANAGHOST_REPO="CabanaGhost https://github.com/CUP-ECS/CabanaGhost.git develop"
ACG_REPO="aCG https://github.com/COMPASS-PSAAP/aCG.git feat-initial-compass-run"
