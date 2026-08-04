"""First-party Anthropic platform dependencies that require migration planning."""


def upload_reference_document(client, file_handle):
    return client.beta.files.upload(file=file_handle)


def submit_nightly_batch(client, requests):
    return client.messages.batches.create(requests=requests)
