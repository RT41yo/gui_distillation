import pyatspi

desktop = pyatspi.Registry.getDesktop(0)

for app in desktop:
    if app is None:
        continue

    try:
        app_name = app.name or ""
        app_role = app.getRoleName()
        app_child_count = app.childCount
    except Exception as exc:
        print(f"app read failed: {exc}")
        continue

    print(f"name={app_name!r} role={app_role!r} childCount={app_child_count}")

    try:
        for i in range(min(app.childCount, 10)):
            child = app.getChildAtIndex(i)
            print(
                f"  child[{i}] "
                f"name={child.name!r} "
                f"role={child.getRoleName()!r} "
                f"childCount={child.childCount}"
            )
    except Exception as exc:
        print(f"  children read failed: {exc}")
