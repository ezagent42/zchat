use serde::Deserialize;

#[derive(Deserialize, Clone, Debug)]
pub struct CommandInfo {
    pub name: String,
    pub args: Vec<ArgInfo>,
}

#[derive(Deserialize, Clone, Debug)]
pub struct ArgInfo {
    pub name: String,
    pub required: bool,
    #[serde(default)]
    pub source: Option<String>,
    /// Pre-resolved choices from CLI (for static sources like servers).
    #[serde(default)]
    pub choices: Vec<String>,
}

/// Parse commands JSON from the inline config string.
pub fn parse_commands(json_str: &str) -> Option<Vec<CommandInfo>> {
    serde_json::from_str(json_str).ok()
}

/// Extract command names from parsed commands.
pub fn command_names(commands: &[CommandInfo]) -> Vec<String> {
    commands.iter().map(|c| c.name.clone()).collect()
}

/// Build the zchat CLI invocation for a command.
/// collected_args is (name, value, required). Required args are positional,
/// optional args are passed as --name value.
pub fn build_cli_args(
    zchat_bin: &str,
    project_name: &str,
    command_name: &str,
    collected_args: &[(String, String, bool)],
) -> Vec<String> {
    let mut cmd: Vec<String> = zchat_bin.split_whitespace().map(String::from).collect();
    if !project_name.is_empty() {
        cmd.push("--project".to_string());
        cmd.push(project_name.to_string());
    }
    cmd.extend(command_name.split_whitespace().map(String::from));
    // Positional (required) args first, then --flag optional args
    for (_, value, required) in collected_args {
        if *required {
            cmd.push(value.clone());
        }
    }
    for (name, value, required) in collected_args {
        if !*required {
            let flag = format!("--{}", name.replace('_', "-"));
            cmd.push(flag);
            cmd.push(value.clone());
        }
    }
    cmd
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_JSON: &str = r#"[
        {"name": "agent create", "args": [
            {"name": "name", "required": true},
            {"name": "workspace", "required": false}
        ]},
        {"name": "agent stop", "args": [
            {"name": "name", "required": true, "source": "running_agents"}
        ]},
        {"name": "shutdown", "args": []}
    ]"#;

    #[test]
    fn parse_commands_from_json() {
        let cmds = parse_commands(SAMPLE_JSON).unwrap();
        assert_eq!(cmds.len(), 3);
        assert_eq!(cmds[0].name, "agent create");
        assert_eq!(cmds[2].name, "shutdown");
    }

    #[test]
    fn parse_commands_extracts_args() {
        let cmds = parse_commands(SAMPLE_JSON).unwrap();
        let create = &cmds[0];
        assert_eq!(create.args.len(), 2);
        assert!(create.args[0].required);
        assert!(!create.args[1].required);
        assert!(create.args[0].source.is_none());
    }

    #[test]
    fn parse_commands_extracts_source() {
        let cmds = parse_commands(SAMPLE_JSON).unwrap();
        let stop = &cmds[1];
        assert_eq!(stop.args[0].source.as_deref(), Some("running_agents"));
    }

    #[test]
    fn parse_commands_invalid_json_returns_none() {
        assert!(parse_commands("not json").is_none());
        assert!(parse_commands("").is_none());
    }

    #[test]
    fn command_names_extracts_names() {
        let cmds = parse_commands(SAMPLE_JSON).unwrap();
        let names = command_names(&cmds);
        assert_eq!(names, vec!["agent create", "agent stop", "shutdown"]);
    }

    #[test]
    fn build_cli_args_with_project() {
        let args = build_cli_args(
            "/usr/bin/zchat", "local", "agent create",
            &[("name".into(), "myagent".into(), true)],
        );
        assert_eq!(args, vec!["/usr/bin/zchat", "--project", "local", "agent", "create", "myagent"]);
    }

    #[test]
    fn build_cli_args_without_project() {
        let args = build_cli_args("zchat", "", "shutdown", &[]);
        assert_eq!(args, vec!["zchat", "shutdown"]);
    }

    #[test]
    fn build_cli_args_multiword_bin() {
        let args = build_cli_args(
            "/usr/bin/python -m zchat.cli", "dev", "agent stop",
            &[("name".into(), "a0".into(), true)],
        );
        assert_eq!(args, vec!["/usr/bin/python", "-m", "zchat.cli", "--project", "dev", "agent", "stop", "a0"]);
    }

    #[test]
    fn build_cli_args_optional_flags() {
        let args = build_cli_args(
            "zchat", "local", "project create",
            &[
                ("name".into(), "myproj".into(), true),
                ("server".into(), "cloud".into(), false),
                ("channels".into(), "#dev".into(), false),
            ],
        );
        assert_eq!(args, vec![
            "zchat", "--project", "local", "project", "create",
            "myproj",                          // positional
            "--server", "cloud",               // optional flag
            "--channels", "#dev",              // optional flag
        ]);
    }

    #[test]
    fn build_cli_args_skips_empty_optional() {
        // Empty optional args should not be in collected_args at all
        // (palette skips them), so this just verifies no optional = no flags
        let args = build_cli_args(
            "zchat", "", "agent create",
            &[("name".into(), "a0".into(), true)],
        );
        assert_eq!(args, vec!["zchat", "agent", "create", "a0"]);
    }

    #[test]
    fn parse_commands_with_choices() {
        let json = r#"[{"name": "project create", "args": [
            {"name": "name", "required": true},
            {"name": "server", "required": false, "source": "servers", "choices": ["cloud", "local"]}
        ]}]"#;
        let cmds = parse_commands(json).unwrap();
        let server_arg = &cmds[0].args[1];
        assert_eq!(server_arg.source.as_deref(), Some("servers"));
        assert_eq!(server_arg.choices, vec!["cloud", "local"]);
    }

    #[test]
    fn parse_commands_missing_choices_defaults_empty() {
        let json = r#"[{"name": "shutdown", "args": [{"name": "x", "required": true}]}]"#;
        let cmds = parse_commands(json).unwrap();
        assert!(cmds[0].args[0].choices.is_empty());
    }

    #[test]
    fn parse_escaped_json_from_kdl() {
        // Simulate what KDL does: the CLI escapes quotes, KDL unescapes them back
        // So the plugin receives valid JSON in the configuration map
        let json = r#"[{"name":"agent create","args":[{"name":"name","required":true}]}]"#;
        let cmds = parse_commands(json).unwrap();
        assert_eq!(cmds.len(), 1);
        assert_eq!(cmds[0].name, "agent create");
    }
}
