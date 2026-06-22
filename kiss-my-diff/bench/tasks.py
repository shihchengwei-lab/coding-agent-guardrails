def select_task_ids(tasks, suite=None):
    selected = []
    for task_id, task in sorted(tasks.items()):
        if suite is not None and task.get("suite") != suite:
            continue
        selected.append(task_id)
    return selected
