# Wheeltec backend provenance

Imported 2026-09-24 from UGV_004 read-only `/home/nrc15/livox_fastlio/src/fast_lio_localization`.
The installed device checkout has no reliable upstream revision; the original bytes are pinned below.
Local adaptations are maintained inside `EPGeneral_relocalization`; no separate ROS package is introduced.

- Original package: GPL version 3; full text in `LICENSE`.
- `pclomp` files: BSD 3-clause notices retained in each source/header (Koide et al.; PCL).
- Local gate adaptation and tests: GPL-3.0-only. The existing Python coordinator retains Apache-2.0.

| Imported path | Original SHA-256 |
| --- | --- |
| `LICENSE` | `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` |
| `src/fast_lio_localization.cpp` | `0f4920937d43669a8b630edd2d2b87c494b40d170a4ab304f087a9b6664a5635` |
| `include/fast_lio_localization/allowed_regions.h` | `90f885c2af8bf2ea09a2219896baba39b5497d3aed86ee2cea5ada6f3449392b` |
| `include/pclomp/ndt_omp.h` | `e262c960fbfed3a0dc1c101654d4e4fd930c2cefc3797643cbd159648e15addc` |
| `include/pclomp/ndt_omp_impl.hpp` | `af1363c446ac188653c2e4ebef2b1e48fa00e491c1f4cec2fd9cc17a782d4e86` |
| `include/pclomp/voxel_grid_covariance_omp.h` | `cc4bdccae332d7b464bc505a3dd28a9c856c8f7be286ba7f5d271ea2e7fb78e4` |
| `include/pclomp/voxel_grid_covariance_omp_impl.hpp` | `4f71cc8e59c9401cac97cd18501253c02dbfa1f84a689b88f9842994fab228d1` |
| `src/pclomp/ndt_omp.cpp` | `e0f6d1d37f3360433558188d4409772d5e2b89edb01c5ce42b5d54ec0ab45a8b` |
| `src/pclomp/voxel_grid_covariance_omp.cpp` | `4ba436f5381e69d6fc8a53d63351a6a27be0afac42d48c3913be1924eca253ae` |
