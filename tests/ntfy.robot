*** Settings ***
Library    SSHLibrary
Library    String

*** Variables ***
${IMAGE_URL}         ghcr.io/platypuschan/ntfy-reworked:latest
# The upgrade scenario starts from the last published release of this module;
# test-module-upgrade.sh looks it up in the registry.
${PREVIOUS_IMAGE_URL}    ${EMPTY}
${SCENARIO}          install
${HOST}              ntfy.test
${module_id}         ${EMPTY}
${web_port}          ${EMPTY}
${ADMIN_USER}        admin
${ADMIN_PASSWORD}    Nethesis,1234

*** Keywords ***
Login to cluster-admin
    New Page    https://${NODE_ADDR}/cluster-admin/
    Fill Text    text="Username"    ${ADMIN_USER}
    Click    button >> text="Continue"
    Fill Text    text="Password"    ${ADMIN_PASSWORD}
    Click    button >> text="Log in"
    Wait For Elements State    css=#main-content    visible    timeout=10s

ntfy health endpoint is reachable
    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 5 http://127.0.0.1:${web_port}/v1/health
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    "healthy":true

Wait until ntfy is healthy
    Wait Until Keyword Succeeds    120 seconds    2 seconds    ntfy health endpoint is reachable

Read allocated web port
    ${port} =    Execute Command    runagent -m ${module_id} printenv TCP_PORT
    ${port} =    Strip String    ${port}
    Should Match Regexp    ${port}    ^[0-9]+$
    Set Suite Variable    ${web_port}    ${port}

Configure current module with test server.yml
    ${server_config} =    Catenate    SEPARATOR=\n
    ...    base-url: "http://${HOST}"
    ...    cache-file: "/var/lib/ntfy/cache.db"
    ...    attachment-cache-dir: "/var/lib/ntfy/attachments"
    ...    behind-proxy: false
    ...    proxy-forwarded-header: "X-Real-IP"
    ${payload} =    Evaluate    json.dumps({"host": $HOST, "http2https": False, "lets_encrypt": False, "server_config": $server_config})    modules=json
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    configure-module failed: ${output}

*** Test Cases ***
Add module for ${SCENARIO} scenario
    IF    r'${SCENARIO}' == 'upgrade'
        Set Local Variable    ${install_image}    ${PREVIOUS_IMAGE_URL}
    ELSE
        Set Local Variable    ${install_image}    ${IMAGE_URL}
    END
    ${output}    ${rc} =    Execute Command    add-module ${install_image} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module ${install_image} failed: ${output}
    &{output} =    Evaluate    ast.literal_eval(r'''${output}''')    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}

Configure initial module
    Configure current module with test server.yml
    IF    r'${SCENARIO}' == 'upgrade'
        # Leave a message in the SQLite cache and a file in the data volume.
        Read allocated web port
        Wait until ntfy is healthy
        ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 -d 'before-upgrade' http://127.0.0.1:${web_port}/ci-before-upgrade
        ...    return_rc=True
        Should Be Equal As Integers    ${rc}    0    publish before upgrade failed: ${output}
        ${rc} =    Execute Command    runagent -m ${module_id} podman unshare sh -c 'm="$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)"; mkdir -p "$m/attachments" && echo before-upgrade > "$m/attachments/ci-upgrade-marker"'
        ...    return_rc=True    return_stdout=False
        Should Be Equal As Integers    ${rc}    0
    END

Update module from the previous release
    Skip If    r'${SCENARIO}' != 'upgrade'    only the upgrade scenario updates the module
    Log    Scenario ${SCENARIO} with ${IMAGE_URL}    console=${True}
    # Same request as the Software Center: no forced pull.
    ${output}    ${rc} =    Execute Command    api-cli run update-module --data '{"module_url":"${IMAGE_URL}","instances":["${module_id}"]}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    update-module ${IMAGE_URL} failed: ${output}
    ${journal} =    Execute Command    journalctl -q --no-pager SYSLOG_IDENTIFIER=agent@${module_id}
    Should Not Contain    ${journal}    has failed    an update-module.d step failed
    ${image} =    Execute Command    runagent -m ${module_id} printenv IMAGE_URL
    ${image} =    Strip String    ${image}
    Should Be Equal    ${image}    ${IMAGE_URL}

Check service health after install or update
    Read allocated web port
    Wait until ntfy is healthy

Check data kept by the upgrade
    Skip If    r'${SCENARIO}' != 'upgrade'    only the upgrade scenario has data from the previous release
    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 'http://127.0.0.1:${web_port}/ci-before-upgrade/json?poll=1'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    poll after upgrade failed: ${output}
    Should Contain    ${output}    "message":"before-upgrade"
    ${output}    ${rc} =    Execute Command    runagent -m ${module_id} podman unshare sh -c 'cat "$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)/attachments/ci-upgrade-marker"'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    volume file lost by the upgrade: ${output}
    Should Be Equal    ${output}    before-upgrade

Check server.yml persistence and read-only mount
    ${mode} =    Execute Command    runagent -m ${module_id} stat -c '%a' config/server.yml
    ${mode} =    Strip String    ${mode}
    Should Be Equal    ${mode}    600

    ${config} =    Execute Command    runagent -m ${module_id} cat config/server.yml
    Should Contain    ${config}    cache-file: "/var/lib/ntfy/cache.db"
    Should Contain    ${config}    behind-proxy: false

    ${read_write} =    Execute Command    runagent -m ${module_id} podman inspect ntfy-app --format '{{range .Mounts}}{{if eq .Destination "/etc/ntfy"}}{{println .RW}}{{end}}{{end}}'
    ${read_write} =    Strip String    ${read_write}
    Should Be Equal    ${read_write}    false

Check enforced NS8 proxy settings
    ${environment} =    Execute Command    runagent -m ${module_id} podman exec ntfy-app env
    Should Contain    ${environment}    NTFY_BEHIND_PROXY=true
    Should Contain    ${environment}    NTFY_PROXY_FORWARDED_HEADER=X-Forwarded-For

Check public HTTP route
    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 --resolve ${HOST}:80:127.0.0.1 http://${HOST}/v1/health
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    "healthy":true

Publish and subscribe through Traefik
    ${topic} =    Set Variable    ci-${SCENARIO}
    ${message} =    Set Variable    qemu-${SCENARIO}-message
    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 --resolve ${HOST}:80:127.0.0.1 -d '${message}' http://${HOST}/${topic}
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    publish failed: ${output}

    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 --resolve ${HOST}:80:127.0.0.1 'http://${HOST}/${topic}/json?poll=1'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    subscribe failed: ${output}
    Should Contain    ${output}    "message":"${message}"

Check ntfy data is stored in the backed up volume
    ${rc} =    Execute Command    runagent -m ${module_id} sh -c 'test -f "$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)/cache.db"'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    cache.db is not in the ntfy-data volume
    ${rc} =    Execute Command    runagent -m ${module_id} test ! -e cache.db
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    cache.db is still in the state directory
    ${include} =    Execute Command    runagent -m ${module_id} sh -c 'cat ../etc/state-include.conf'
    Should Contain    ${include}    volumes/ntfy-data/.ntfy-backup-snapshot

Check backup snapshot and service restart
    # Attachments are hard-linked into the snapshot inside Podman's user namespace
    ${rc} =    Execute Command    runagent -m ${module_id} podman unshare sh -c 'm="$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)"; mkdir -p "$m/attachments" && echo ci > "$m/attachments/ci-link"'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${module_id} module-dump-state
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    ntfy snapshot failed
    ${snapshot} =    Execute Command    runagent -m ${module_id} sh -c 'cat "$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)/.ntfy-backup-snapshot/server.yml"'
    Should Contain    ${snapshot}    cache-file: "/var/lib/ntfy/cache.db"
    ${rc} =    Execute Command    runagent -m ${module_id} sh -c 'test -f "$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)/.ntfy-backup-snapshot/data/cache.db"'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    snapshot has no SQLite database
    ${rc} =    Execute Command    runagent -m ${module_id} podman unshare sh -c 'm="$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)"; test "$m/attachments/ci-link" -ef "$m/.ntfy-backup-snapshot/data/attachments/ci-link" && test ! "$m/cache.db" -ef "$m/.ntfy-backup-snapshot/data/cache.db"'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    attachments are not hard-linked or cache.db is not a copy
    Wait until ntfy is healthy
    ${rc} =    Execute Command    runagent -m ${module_id} module-cleanup-state
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    snapshot cleanup failed
    ${rc} =    Execute Command    runagent -m ${module_id} sh -c 'test ! -e "$(podman volume inspect --format "{{.Mountpoint}}" ntfy-data)/.ntfy-backup-snapshot"'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0    temporary snapshot remains after cleanup

Module UI loads in cluster-admin
    [Tags]    ui
    Import Library    Browser
    New Browser    chromium    headless=True
    New Context    ignoreHTTPSErrors=True
    Login to cluster-admin
    Go To    https://${NODE_ADDR}/cluster-admin/#/apps/${module_id}
    Wait For Elements State    iframe >>> h2 >> text="Status"    visible    timeout=20s
    Take Screenshot    filename=${OUTPUT DIR}/browser/screenshot/1._Status.png
    Go To    https://${NODE_ADDR}/cluster-admin/#/apps/${module_id}?page=settings
    Wait For Elements State    iframe >>> h2 >> text="Settings"    visible    timeout=20s
    Take Screenshot    filename=${OUTPUT DIR}/browser/screenshot/2._Settings.png
    Close Browser

Remove module
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
