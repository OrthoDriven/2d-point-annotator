from pathlib import Path


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except ImportError:
        config = {}
        for line in config_path.read_text().splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if v.startswith("[") and v.endswith("]"):
                    v = [i.strip().strip('"').strip("'") for i in v[1:-1].split(",")]
                elif v.isdigit():
                    v = int(v)
                config[k] = v
        return config
