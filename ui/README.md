# NS8 ntfy UI development

To develop ntfy UI please refer to [this section of the Developer manual](https://nethserver.github.io/ns8-core/ui/modules/#module-ui-development).

The UI imports the shared reserved-option policy from
`../imageroot/pypkg/ntfy_config_policy.json`. Keep the whole repository available
when building or mounting the UI development container. Run `yarn test` for the
browser-side YAML validator, followed by `yarn lint` and `yarn build`.
