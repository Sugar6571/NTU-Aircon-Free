try:
    import ujson as json
except ImportError:
    import json

from src.utils import join_path


PROFILE_ROOT = "/ir_profiles"


def profile_dir(profile_name):
    return join_path(PROFILE_ROOT, profile_name)


def profile_json_path(profile_name):
    return join_path(profile_dir(profile_name), "profile.json")


def load_profile(profile_name):
    try:
        with open(profile_json_path(profile_name), "r") as f:
            return json.loads(f.read())
    except OSError:
        return None
    except ValueError:
        return None


def command_file(profile, command_name):
    commands = profile.get("commands", {})
    command = commands.get(command_name)
    if not command:
        return None
    return command.get("file")


def command_path(profile_name, profile, command_name):
    filename = command_file(profile, command_name)
    if not filename:
        return None
    return join_path(profile_dir(profile_name), filename)


def default_profile(profile_name):
    return {
        "profile_name": profile_name,
        "brand": "",
        "location_context": "",
        "notes": "",
        "strong_can_power_on": True,
        "power_off_reliable": False,
        "commands": {},
    }


def save_profile(profile_name, profile):
    with open(profile_json_path(profile_name), "w") as f:
        f.write(json.dumps(profile))


def ensure_profile(profile_name):
    profile = load_profile(profile_name)
    if profile:
        return profile
    profile = default_profile(profile_name)
    save_profile(profile_name, profile)
    return profile


def set_command(profile_name, profile, command_name, filename, description=""):
    if "commands" not in profile:
        profile["commands"] = {}
    profile["commands"][command_name] = {
        "file": filename,
        "description": description,
    }
    save_profile(profile_name, profile)
