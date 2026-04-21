# Changelog

## [2.5.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.4.1...v2.5.0) (2026-04-21)


### Features

* **data:** Load balancing data based on current values in remote ([2180735](https://github.com/OrthoDriven/2d-point-annotator/commit/218073536df9add3587756d90484a98112d59bab))


### Bug Fixes

* **auth:** Adding ipv4 fallback for more robust connection. ([5c3e7a5](https://github.com/OrthoDriven/2d-point-annotator/commit/5c3e7a53811bf3cf53fffb3b7b8e1f6a13098a48))
* **circle:** Fixing circle rendering, fix round_1 image order ([fbfecca](https://github.com/OrthoDriven/2d-point-annotator/commit/fbfecca4fa823a6618a978a6063a552157682538))
* **circle:** Fixing circle rendering, fix round_1 image order ([1aac5a8](https://github.com/OrthoDriven/2d-point-annotator/commit/1aac5a8dab2c85b674b157030391a83605b696c3))
* **data:** Some corrections to the load balancing algorithms. ([9912326](https://github.com/OrthoDriven/2d-point-annotator/commit/99123268e733a8312984596c2436c52004b6aa2e))
* **data:** Some corrections to the load balancing algorithms. ([fb99d3a](https://github.com/OrthoDriven/2d-point-annotator/commit/fb99d3af69d4991f63a425baec7965493c0c9b61))
* **ui:** dynamic panel width in lower resolution monitors ([b24d757](https://github.com/OrthoDriven/2d-point-annotator/commit/b24d757b7ddbb66de2ef9028a0aea7574a041302))

## [2.4.1](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.4.0...v2.4.1) (2026-04-18)


### Bug Fixes

* **ui:** zoom window hover circle update on scroll ([8c57bdd](https://github.com/OrthoDriven/2d-point-annotator/commit/8c57bddbd4a01a2c63f33600308964b16cf985d3))

## [2.4.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.3.0...v2.4.0) (2026-04-18)


### Features

* annotation progress report ([ef73b7d](https://github.com/OrthoDriven/2d-point-annotator/commit/ef73b7d9adf75284d03067bf9547cdbce2f043cc))
* **review:** Adding a button to submit an image for review ([0a16316](https://github.com/OrthoDriven/2d-point-annotator/commit/0a1631615a35ea6f91b86a779077907939b3fe76))
* **ui:** Add hover circle in zoom view. ([20b26a8](https://github.com/OrthoDriven/2d-point-annotator/commit/20b26a85dfe3854d39080a4ad9de15ebe3232c2c))
* **ui:** Add persistent hover circle for FHC and AC landmarks. ([3153efd](https://github.com/OrthoDriven/2d-point-annotator/commit/3153efd7250325119a532d2ae082971ebadcf54a))
* **ui:** Percentile based contrast enhancement. ([f73f5fb](https://github.com/OrthoDriven/2d-point-annotator/commit/f73f5fb90b7adaac78e75f715af73fd7795a5a69))


### Bug Fixes

* Fixed landmark overflow in "upload for review" ([52426fd](https://github.com/OrthoDriven/2d-point-annotator/commit/52426fda319d67486060687c8f3fd2ba6218f668))
* **report:** fixed some hard-coded paths in the progress report ([be5e83b](https://github.com/OrthoDriven/2d-point-annotator/commit/be5e83b98e794fe0efde6554567564e67f2ed73f))

## [2.3.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.2.0...v2.3.0) (2026-04-17)


### Features

* **canvas:** add pixel-art scaling (Scale2x) toggle for zoom window ([e3ee687](https://github.com/OrthoDriven/2d-point-annotator/commit/e3ee687341effeffb7eadd1805577d1a8eb43e23))
* **canvas:** apply CLAHE to zoom view when enabled ([c6f9199](https://github.com/OrthoDriven/2d-point-annotator/commit/c6f919972169b065ffc97362d9c8be634e2df5de))
* **ui:** add zoom contrast toggle to left panel ([c6f9199](https://github.com/OrthoDriven/2d-point-annotator/commit/c6f919972169b065ffc97362d9c8be634e2df5de))

## [2.2.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.1.1...v2.2.0) (2026-04-16)


### Features

* **dev:** Added a nightly feature so that dev can pull from main ([1f9950e](https://github.com/OrthoDriven/2d-point-annotator/commit/1f9950e3cb7cf1c1904f4b733d5f072e7b6b3e31))


### Bug Fixes

* **auth:** fixed auth file locks ([4e201f8](https://github.com/OrthoDriven/2d-point-annotator/commit/4e201f8335687859ab5b4065b7a050bfdb183df6))
* **docs:** storing app version per-image, not on full json ([f6fb908](https://github.com/OrthoDriven/2d-point-annotator/commit/f6fb908f4131a1506dd09e4c419edc9545ab5ad4))
* **docs:** storing app version per-image, not on full json ([b3b5ff6](https://github.com/OrthoDriven/2d-point-annotator/commit/b3b5ff6ea719a7f0b8cd21d5995dd810b16d8f81))
* **landmark:** Add L/R PS landmarks in unilateral views. ([c868256](https://github.com/OrthoDriven/2d-point-annotator/commit/c868256674ca062e1eaff5f0062a7eed8fe133ef))
* **test:** Fixing onedrive tests that hang when no auth client provided ([1034084](https://github.com/OrthoDriven/2d-point-annotator/commit/103408483b406a48ad10a1db15ddb551d3f7d19e))
* **test:** Fixing onedrive tests that hang when no auth client provided ([6684a8b](https://github.com/OrthoDriven/2d-point-annotator/commit/6684a8b22d1cc8ff6bea909aa649e25314bc32a1))
* **ui:** Added "whiskers" to femoral axis tool description ([3fd086c](https://github.com/OrthoDriven/2d-point-annotator/commit/3fd086c39a86896d19a234fa9a42cd61ba08c521))
* **ui:** Landmark display order ([9350a40](https://github.com/OrthoDriven/2d-point-annotator/commit/9350a40ee770d589994806fe071e01257d34f79b))
* **ux:** Single-sided landmark keyboard navigation includes full set ([4872163](https://github.com/OrthoDriven/2d-point-annotator/commit/4872163850e413ee983deec2a14ee778f8d966cb))
* **version:** Adding .release-please-manifest.json as version GT ([4bdf277](https://github.com/OrthoDriven/2d-point-annotator/commit/4bdf27701695c579b25d9f32463f8f481ff69175))

## [2.1.1](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.1.0...v2.1.1) (2026-04-14)


### Bug Fixes

* **io:** Make image loading work in flat json hierarchy and relative ([0367fd1](https://github.com/OrthoDriven/2d-point-annotator/commit/0367fd1b0ed46042a40ec0546582f18a9c1c3751))
* **io:** Make image loading work in flat json hierarchy and relative hierarchy. ([f17d9a6](https://github.com/OrthoDriven/2d-point-annotator/commit/f17d9a6be1e05525d4f0917613fbdbbfbc22ec79))
* Removing unused and test files scattered around. ([10edbca](https://github.com/OrthoDriven/2d-point-annotator/commit/10edbcaddf10bdf439fd3578e2cd4d98f1b689ea))

## [2.1.0](https://github.com/OrthoDriven/2d-point-annotator/compare/v2.0.1...v2.1.0) (2026-04-14)


### Features

* **repro:** Adding study generation configuration for traceability. ([888a9f3](https://github.com/OrthoDriven/2d-point-annotator/commit/888a9f3bdea4cc283ea6f8285f62e1af6e410159))
* **repro:** Adding study generation configuration for traceability. ([2d4f763](https://github.com/OrthoDriven/2d-point-annotator/commit/2d4f763654888a3c962f788573b45efb01f91e36))
* **tools:** add landmark reference lookup module ([9dc9808](https://github.com/OrthoDriven/2d-point-annotator/commit/9dc98089731bbf2098344c9ebf54c66e0d8202e2))
* **ui:** Add protocol version to the UI front end. ([7a97b8d](https://github.com/OrthoDriven/2d-point-annotator/commit/7a97b8d7a846968e4ef1ca50d918f5a64149488e))
* **ui:** Add protocol version to the UI front end. ([63a5caa](https://github.com/OrthoDriven/2d-point-annotator/commit/63a5caa124e277690197ca631d9952249a1f77da))
* **ui:** Data downloader ([0d72a15](https://github.com/OrthoDriven/2d-point-annotator/commit/0d72a158f063c2ac037a68139250a05f4d9faf96))


### Bug Fixes

* **data:** prevent Windows hang on close and fix asyncio event loop leaks ([6a61c32](https://github.com/OrthoDriven/2d-point-annotator/commit/6a61c32e2793a8f6082016e3d3a86c22f0ffd329))
* Fixing print thread race conditions inside async onedrive fn. ([2c35f8f](https://github.com/OrthoDriven/2d-point-annotator/commit/2c35f8f4a6f4de28a07a2d0eb8f65ac388b01474))
* made the onedrive downloading faster ([b4a9a03](https://github.com/OrthoDriven/2d-point-annotator/commit/b4a9a0372c2241bc753d2e854b41fb9ba1c9fd4e))

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
