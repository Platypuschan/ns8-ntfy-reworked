*** Settings ***
Library    SSHLibrary
Library    String

*** Variables ***
${IMAGE_URL}         ghcr.io/platypuschan/ntfy:latest
${BASELINE_IMAGE}    ghcr.io/geniusdynamics/ntfy:latest
${SCENARIO}          install
${HOST}              ntfy.test
${module_id}         ${EMPTY}
${web_port}          ${EMPTY}

*** Keywords ***
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
    ${payload} =    Evaluate    json.dumps({"host": "${HOST}", "http2https": False, "lets_encrypt": False, "server_config": """${server_config}"""})    modules=json
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    configure-module failed: ${output}

*** Test Cases ***
Add module for ${SCENARIO} scenario
    IF    r'${SCENARIO}' == 'update'
        Set Local Variable    ${install_image}    ${BASELINE_IMAGE}
    ELSE
        Set Local Variable    ${install_image}    ${IMAGE_URL}
    END
    ${output}    ${rc} =    Execute Command    add-module ${install_image} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module ${install_image} failed: ${output}
    &{output} =    Evaluate    ast.literal_eval(r'''${output}''')    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}

Configure initial module
    IF    r'${SCENARIO}' == 'update'
        ${payload} =    Evaluate    json.dumps({"host": "${HOST}", "http2https": False, "lets_encrypt": False})    modules=json
        ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
        ...    return_rc=True
        Should Be Equal As Integers    ${rc}    0    baseline configure-module failed: ${output}
    ELSE
        Configure current module with test server.yml
    END

Update module and migrate legacy configuration
    Log    Scenario ${SCENARIO} with ${IMAGE_URL}    console=${True}
    IF    r'${SCENARIO}' == 'update'
        ${output}    ${rc} =    Execute Command    api-cli run update-module --data '{"force":true,"module_url":"${IMAGE_URL}","instances":["${module_id}"]}'
        ...    return_rc=True
        Should Be Equal As Integers    ${rc}    0    update-module ${IMAGE_URL} failed: ${output}

        ${payload} =    Evaluate    json.dumps({"host": "${HOST}", "http2https": False, "lets_encrypt": False})    modules=json
        ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
        ...    return_rc=True
        Should Be Equal As Integers    ${rc}    0    migration configure-module failed: ${output}

        ${migration_size} =    Execute Command    runagent -m ${module_id} stat -c '%s' config/server.yml
        ${migration_size} =    Strip String    ${migration_size}
        Should Match Regexp    ${migration_size}    ^[1-9][0-9]*$

        Configure current module with test server.yml
    END

Check service health after install or update
    Read allocated web port
    Wait until ntfy is healthy

Check server.yml persistence and read-only mount
    ${mode} =    Execute Command    runagent -m ${module_id} stat -c '%a' config/server.yml
    ${mode} =    Strip String    ${mode}
    Should Be Equal    ${mode}    600

    ${config} =    Execute Command    runagent -m ${module_id} cat config/server.yml
    Should Contain    ${config}    cache-file: "/var/lib/ntfy/cache.db"
    Should Contain    ${config}    behind-proxy: false

    ${mounted_config} =    Execute Command    runagent -m ${module_id} podman exec ntfy-app cat /etc/ntfy/server.yml
    Should Be Equal    ${mounted_config}    ${config}

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

Remove module
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
