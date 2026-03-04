from nanobot.config.loader import load_config

if __name__ == "__main__":
    config = load_config()
    print("DingTalk config:")
    print("Enabled:", config.channels.dingtalk.enabled)
    print("Master IDs:", config.channels.dingtalk.master_ids)
