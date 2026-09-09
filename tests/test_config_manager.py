from haven_backup.config_manager import ConfigManager


def test_default_config_created_on_first_load(tmp_path):
    config_file = str(tmp_path / "config.json")
    config = ConfigManager(config_file)
    assert config.get_backup_paths() == []
    assert config.get_destination()["type"] == "local"


def test_settings_persist_across_instances(tmp_path):
    config_file = str(tmp_path / "config.json")
    ConfigManager(config_file).set_backup_paths(["/etc", "/etc/pve"])

    reloaded = ConfigManager(config_file)
    assert reloaded.get_backup_paths() == ["/etc", "/etc/pve"]


def test_set_destination_sftp_round_trips(tmp_path):
    config_file = str(tmp_path / "config.json")
    config = ConfigManager(config_file)
    config.set_destination_sftp(host="backup.example.com", username="haven", remote_path="/backups/host1")

    dest = ConfigManager(config_file).get_destination()
    assert dest["type"] == "sftp"
    assert dest["host"] == "backup.example.com"
    assert dest["port"] == 22
