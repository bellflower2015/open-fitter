@echo off
echo Running splitter_linker_global.py...
python splitter_linker_global.py
if %errorlevel% neq 0 exit /b %errorlevel%

echo Running ruff check (1/3)...
ruff check ./extracted --select F401,I --fix
if %errorlevel% neq 0 exit /b %errorlevel%

echo Running orphan_remover.py...
python orphan_remover.py
if %errorlevel% neq 0 exit /b %errorlevel%

echo Running organize_extracted.py...
python organize_extracted.py
if %errorlevel% neq 0 exit /b %errorlevel%

echo Running ruff check (2/3)...
ruff check ./extracted --select F401,I --fix
if %errorlevel% neq 0 exit /b %errorlevel%

echo Running orphan_remover.py...
python orphan_remover.py
if %errorlevel% neq 0 exit /b %errorlevel%

echo Running ruff check (3/3)...
ruff check ./extracted --select F401,I --fix
if %errorlevel% neq 0 exit /b %errorlevel%

echo Done.
