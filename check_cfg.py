from nanobot.config.loader import load_config

if __name__ == "__main__":
    config = load_config()
    print("Channels config:")
    for chan_name in ["dingtalk", "cli"]:
        chan_cfg = getattr(config.channels, chan_name, None)
        if chan_cfg and getattr(chan_cfg, "enabled", False):
            print(f"  {chan_name}:")
            print(f"    Master IDs: {getattr(chan_cfg, 'master_ids', 'N/A')}")
        else:
            print(f"  {chan_name}: Disabled or Not configured")
