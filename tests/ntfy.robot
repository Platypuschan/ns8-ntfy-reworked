*** Settings ***
Library    SSHLibrary

*** Test Cases ***
Check if ntfy is installed correctly
    ${output}  ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ${output}
    Set Suite Variable    ${module_id}    ${output.module_id}

Check if ntfy can be configured
    ${payload} =    Evaluate    json.dumps({"host": "ntfy.example.org", "http2https": False, "lets_encrypt": False, "server_config": "base-url: http://ntfy.example.org\\nbehind-proxy: true\\ncache-file: /var/lib/ntfy/cache.db\\n"})    modules=json
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if server.yml is mounted
    ${rc} =    Execute Command    runagent -m ${module_id} podman exec ntfy-app grep -F 'behind-proxy: true' /etc/ntfy/server.yml
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if ntfy works as expected
    ${rc} =    Execute Command    curl -f http://127.0.0.1/ntfy/
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if ntfy is removed correctly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
