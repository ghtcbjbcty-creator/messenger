[app]
title = Мессенджер
package.name = messenger
package.domain = org.messenger
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,txt
version = 1.0
requirements = python3==3.11.6,kivy==2.3.0
orientation = portrait
fullscreen = 0
android.api = 31
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
