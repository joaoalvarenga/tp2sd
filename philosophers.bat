@start cmd /c python manager.py --port 8980 --philosophers 5 --duration 30 --token
timeout 1
@start cmd /c python philosopher.py --manager 127.0.0.1:8980 --port 8981
@start cmd /c python philosopher.py --manager 127.0.0.1:8980 --port 8982
@start cmd /c python philosopher.py --manager 127.0.0.1:8980 --port 8983
@start cmd /c python philosopher.py --manager 127.0.0.1:8980 --port 8984
@start cmd /c python philosopher.py --manager 127.0.0.1:8980 --port 8985