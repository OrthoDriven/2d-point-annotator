import hashlib
from pathlib import Path


def check_all_images(fpath: Path, dup_path: Path):
    image_hashes = {}
    duplicates = []

    for root, dirs, files in fpath.walk():
        for file in files:
            current_image_hash = hash_image(Path(root / file))
            if current_image_hash in image_hashes.keys():
                print(f"Found duplicate at {Path(root / file)}")
                print(f"Duplicate of {image_hashes[current_image_hash]}")
                print("========================")
                duplicates.append(Path(root / file))
                fname = Path(root / file).name
                Path(root / file).rename(Path(dup_path / fname))
            else:
                image_hashes[current_image_hash] = Path(root / file)

    print(f"Total duplicates: {len(duplicates)}")


def hash_image(image_path: Path):
    sha256 = hashlib.sha256()
    with open(image_path, "rb") as f:
        while True:
            data = f.read()
            if not data:
                break
            sha256.update(data)

    return sha256.hexdigest()


def main():
    image_dir = Path(
        "/home/ajj/Documents/ODI/Data/DeanLateralImages/tif_output/compressed_512_tifs/ALL_DATA/seated/unknown/"
    )
    duplicates_dir = Path(image_dir / "duplicates")
    duplicates_dir.mkdir(exist_ok=True)

    check_all_images(image_dir, duplicates_dir)


if __name__ == "__main__":
    main()
