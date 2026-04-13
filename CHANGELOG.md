# Changelog

## [2.0.1](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.0.0...v2.0.1) (2026-04-13)


### Bug Fixes

* **ui:** Added "Not FDA approved" on home screen. ([ee8ba41](https://github.com/OrthoDriven/2d-point-annotator/commit/ee8ba412fb518d963b94e0b9777ba49b00c69965))

## [2.0.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.4.4...v2.0.0) (2026-04-13)


### ⚠ BREAKING CHANGES

* **data:** adds JSON as primary local annotation format. Existing CSV/SQLite import and OneDrive backup pipeline preserved.

### Features

* **canvas:** add mouse crosshair on main canvas ([b57ac23](https://github.com/OrthoDriven/2d-point-annotator/commit/b57ac23305830e1f876b7fc8efae32f93b25d8e6))
* **canvas:** add right-click state tracking ([58b92e5](https://github.com/OrthoDriven/2d-point-annotator/commit/58b92e508fc295e0c8b641958a59f96066795019))
* **canvas:** enforce left/right landmark ordering ([7897293](https://github.com/OrthoDriven/2d-point-annotator/commit/789729334948f12d3473bef73c6df91d3e896aa9))
* **data:** add JSON annotation format alongside CSV/SQLite ([14cd290](https://github.com/OrthoDriven/2d-point-annotator/commit/14cd290f8a2d20bc18d460b2a998281f4d49728a))
* **data:** add per-image flag checkbox ([152e481](https://github.com/OrthoDriven/2d-point-annotator/commit/152e4813f386a12b680850062f6d7e573e4ae880))
* **data:** add per-landmark flag and note with shortcut blocking ([7c11f58](https://github.com/OrthoDriven/2d-point-annotator/commit/7c11f583ec12ee4bc69497c2904111a76da785bb))
* **scripts:** add image group data generator, default JSON template, fix pixi paths ([0bcf673](https://github.com/OrthoDriven/2d-point-annotator/commit/0bcf673d155699e468dd88059f4c359a47e47d05))
* **tools:** add extended crosshair tool with zoom mirror ([fd02af7](https://github.com/OrthoDriven/2d-point-annotator/commit/fd02af71b88b26634122ed2484911f4e3c9f46e8))
* **tools:** add femoral axis visualization with orthogonal projections ([d3f83ea](https://github.com/OrthoDriven/2d-point-annotator/commit/d3f83eaaa7b2ae53ca3241cc1c80f27a68aa5b94))
* **tools:** add line landmark support for femoral axis ([ca01934](https://github.com/OrthoDriven/2d-point-annotator/commit/ca01934307a62eb5cde02c894209b5e91b35d501))
* **tools:** add zoom landmark overlay with toggle ([189bece](https://github.com/OrthoDriven/2d-point-annotator/commit/189bece08ac81337ed1d45fd95e1df7e2dfc824c))
* **tools:** add zoom panel with magnified view ([eaf558b](https://github.com/OrthoDriven/2d-point-annotator/commit/eaf558ba1e1e4ec924b5dae2d50c6fd848fc9008))
* **tools:** use bicubic resampling in zoom panel ([b536c34](https://github.com/OrthoDriven/2d-point-annotator/commit/b536c3443a925e7f44ea240439fc05531a802518))
* **ui:** display app version in bottom-left of tools panel ([b256175](https://github.com/OrthoDriven/2d-point-annotator/commit/b25617551f6a93a839c257844e9ddf2c2791210c))
* **ui:** restructure to three-column layout ([f6b42d3](https://github.com/OrthoDriven/2d-point-annotator/commit/f6b42d3e0356c567f8c7b56ff230a1b5b310ae94))
* **workflow:** add auto-tool switching on landmark selection ([f18e18a](https://github.com/OrthoDriven/2d-point-annotator/commit/f18e18ad421595089b7c7adb18b82342174cd1e4))
* **workflow:** add autosave toggle checkbox ([98e1749](https://github.com/OrthoDriven/2d-point-annotator/commit/98e17492b646d78c013757d14173199f79a932d0))
* **workflow:** add image list with progress tracking ([682e5d0](https://github.com/OrthoDriven/2d-point-annotator/commit/682e5d08389679c78c5d4e8e49e78d9b0dddea5d))
* **workflow:** add view-based landmark filtering ([1932bed](https://github.com/OrthoDriven/2d-point-annotator/commit/1932bed5c45842ce22ab23d7e769ab943a22815c))


### Bug Fixes

* **canvas:** assign .convert("RGB") return value ([b87a082](https://github.com/OrthoDriven/2d-point-annotator/commit/b87a082b17e64733c3b5db5487c59dcd866cb8f0))
* **canvas:** block line landmark placement on L/R violation and add AP/PA direction ([05c2b73](https://github.com/OrthoDriven/2d-point-annotator/commit/05c2b7389032e8e6909dbf9c406608f4cee7e7b7))
* **data:** debounce OneDrive backup to prevent 409 race conditions ([c151303](https://github.com/OrthoDriven/2d-point-annotator/commit/c151303f06829f0800357be12529dbe70fa96a58))
* **data:** prevent concurrent OneDrive upload threads ([2384f4b](https://github.com/OrthoDriven/2d-point-annotator/commit/2384f4b1d6794a10d78fcc0526bea27e0e4f5931))
* **data:** restore OneDrive backup for JSON saves ([3e0b521](https://github.com/OrthoDriven/2d-point-annotator/commit/3e0b521383be27ccc31aa3f984b6549ad06c3e7a))
* **ui:** make landmark panel header row sticky above scrollable list ([13c513b](https://github.com/OrthoDriven/2d-point-annotator/commit/13c513b7c010c6c150435581da773d4c875c5988))
* **ui:** prevent comboboxes and widgets from stealing keyboard focus ([00438bf](https://github.com/OrthoDriven/2d-point-annotator/commit/00438bf88f18621a3088df7615c7579924018265))

## [1.4.4](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.4.3...v1.4.4) (2026-02-26)


### Bug Fixes

* Add detached-environments setting to config.toml ([ce6f337](https://github.com/OrthoDriven/2d-point-annotator/commit/ce6f337cadf473740e90afbdb79bcbc9eec430d7))
* fixing up windows loading and updating ([e0edbf4](https://github.com/OrthoDriven/2d-point-annotator/commit/e0edbf4c496fc39d6a8b0d5b61cabcc6655d93dc))
* **windows:** fixing the way that windows creates updates. ([3d08340](https://github.com/OrthoDriven/2d-point-annotator/commit/3d083406c3e81f2e3b6b7067b619a28593070ba6))

## [1.4.3](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.4.2...v1.4.3) (2026-02-20)


### Reverts

* removing ttkbootstrap, since this breaks things on MacOS. ([025716c](https://github.com/OrthoDriven/2d-point-annotator/commit/025716c3ceb5e0aa37919c5c50934c9ae0909ce4))
* removing ttkbootstrap, since this breaks things on MacOS. ([8c5485c](https://github.com/OrthoDriven/2d-point-annotator/commit/8c5485c0ee25d0ce6fd192a6f5baacefbfbd2209))

## [1.4.2](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.4.1...v1.4.2) (2026-02-09)


### Bug Fixes

* new ([#36](https://github.com/OrthoDriven/2d-point-annotator/issues/36)) ([ca6a052](https://github.com/OrthoDriven/2d-point-annotator/commit/ca6a052755d033b6832158961ddaa5ba9d831363))
* removing some comments ([#34](https://github.com/OrthoDriven/2d-point-annotator/issues/34)) ([682902f](https://github.com/OrthoDriven/2d-point-annotator/commit/682902f7a194e0a1e76e9c7840d38831ebc15422))

## [1.4.1](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.4.0...v1.4.1) (2026-02-09)


### Bug Fixes

* Add version bump test to test.txt ([#31](https://github.com/OrthoDriven/2d-point-annotator/issues/31)) ([12e7dd3](https://github.com/OrthoDriven/2d-point-annotator/commit/12e7dd395870c3b9cf52537fe69acef6cd4503e5))
* fixing release please code ([#33](https://github.com/OrthoDriven/2d-point-annotator/issues/33)) ([9d7b08d](https://github.com/OrthoDriven/2d-point-annotator/commit/9d7b08d9c2f988b25714b39743714be722ffb85c))

## [1.4.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.3.0...v1.4.0) (2026-02-09)


### Features

* **ui:** changed the core UI engine to ttkbootstrap ([433e37d](https://github.com/OrthoDriven/2d-point-annotator/commit/433e37dbf446bfb6a28b0815425d3f97a27d4128))


### Bug Fixes

* **segmentation:** Don't run segmentation code ([56775c3](https://github.com/OrthoDriven/2d-point-annotator/commit/56775c35c11b97323acf0afdbaff2c00879264b9))

## [1.3.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.2.6...v1.3.0) (2026-02-06)


### Features

* minor version bump ([#24](https://github.com/OrthoDriven/2d-point-annotator/issues/24)) ([1df5505](https://github.com/OrthoDriven/2d-point-annotator/commit/1df55057be4b948dbeb2926e9fb16b8feebc3f29))
* second feature bump ([#26](https://github.com/OrthoDriven/2d-point-annotator/issues/26)) ([dfe7f0d](https://github.com/OrthoDriven/2d-point-annotator/commit/dfe7f0d8e590d2f61ffb5acd345292ef1e4eb232))

## [1.2.6](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.2.5...v1.2.6) (2026-02-06)


### Bug Fixes

* On mac, don't display the window when you're saving. ([e75bf9e](https://github.com/OrthoDriven/2d-point-annotator/commit/e75bf9ef1a63dd7e379c28ca6fbb2ea146507f28))
* On mac, don't display the window when you're saving. ([7f494a2](https://github.com/OrthoDriven/2d-point-annotator/commit/7f494a260c1db1f8eebfa767cbf8c58fea581ada))

## [1.2.5](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.2.4...v1.2.5) (2026-02-06)


### Bug Fixes

* fixing None in db row when exporting to csv ([ca7f0a0](https://github.com/OrthoDriven/2d-point-annotator/commit/ca7f0a0fe6d8479b14e4e9bf698c359f2475e4e8))
* fixing None in db row when exporting to csv ([918d4f1](https://github.com/OrthoDriven/2d-point-annotator/commit/918d4f12265f03aa3b27f7656a5bcfa99de1476d))

## [1.2.4](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.2.3...v1.2.4) (2026-02-06)


### Bug Fixes

* **cleanup:** removing old code that wasn't doing anything ([42a276b](https://github.com/OrthoDriven/2d-point-annotator/commit/42a276b105d692bbc22137e195416e95c18764c4))
* trying to bump the version again with a minor fix ([71da80a](https://github.com/OrthoDriven/2d-point-annotator/commit/71da80ad38c325fdaf8c04436050e5c6f676330b))
* trying to bump the version again with a minor fix ([f0805f9](https://github.com/OrthoDriven/2d-point-annotator/commit/f0805f9bd268f2195ea952a890d32ce62aab8441))

## [1.2.3](https://github.com/OrthoDriven/2d-point-annotator/compare/v1.2.2...v1.2.3) (2026-02-06)


### Bug Fixes

* **test:** testing out a new release ([e0ee791](https://github.com/OrthoDriven/2d-point-annotator/commit/e0ee79184d70e6bea7867ded0f3062d33e387960))
* **test:** testing out a new release ([af07758](https://github.com/OrthoDriven/2d-point-annotator/commit/af0775837282a9a184967f90c63e4c5a5788e8a8))
