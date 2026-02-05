#!/usr/bin/env python3

from math import nan

import polars as pl

df = pl.read_csv("./data/csv/ap_preop.csv")

# df = df.drop(["image_path", "image_quality"])

landmarks = df.columns
landmarks.remove("image_path")
landmarks.remove("image_quality")
ob_landmarks = []

if "LOB" in landmarks:
    # df.drop_in_place("LOB")
    landmarks.remove("LOB")
    ob_landmarks.append("LOB")
if "ROB" in landmarks:
    # df.drop_in_place("ROB")
    landmarks.remove("ROB")
    ob_landmarks.append("ROB")

print(landmarks)

# out = df.with_columns(pl.col(c).list.to_array(2).alias(c + "_arr") for c in landmarks)
out = df.with_columns(
    pl.col(c)
    .str.strip_prefix("[")
    .str.strip_suffix("]")
    .str.split(",")
    .list.eval(pl.element().cast(pl.Float32))
    # .list.to_array(2)
    # .alias(c + "_arr")
    for c in landmarks
)
df = out


out = df.with_columns(
    pl.col(c)
    .str.strip_prefix("[")
    .str.strip_suffix("]")
    .str.split(",")
    .list.eval(pl.element().str.strip_chars())
    .list.slice(0, 2)
    .list.eval(pl.element().cast(pl.Float32))
    # .list.to_array(2)
    # .list.to_struct(
    #     fields=[
    #         "x",
    #         "y",
    #     ]
    # )
    for c in ob_landmarks
)


schema = out.schema
print(schema)
print(out)
paths = out.get_column("image_path")


print(paths[0])

single_row = out.row(0, named=True)
single_row["LASIS"] = [0.0, 0.0]
# dct = {k: pl.Null if not v else [v] for k, v in single_row.items()}

dct = {k: [v] for k, v in single_row.items()}
new_df = pl.DataFrame(dct, nan_to_null=True)
# new_df = pl.DataFrame(row_for_df)
print(new_df)
out = out.update(new_df, on="image_path")
print(out)
