"""
Setup script for building macOS .app bundle
"""
from setuptools import setup

APP = ['training_prompt_app.py']
DATA_FILES = ['Storico_Allenamenti_Garmin.xlsx']
OPTIONS = {
    'argv_emulation': False,
    'packages': ['pandas', 'openpyxl', 'pyperclip'],
    'iconfile': None,
    'plist': {
        'CFBundleName': 'MyTrainingOS',
        'CFBundleDisplayName': 'MyTrainingOS',
        'CFBundleIdentifier': 'com.mytrainingos.promptgenerator',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    }
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
