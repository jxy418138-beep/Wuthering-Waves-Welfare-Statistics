#!/usr/bin/env python3
"""生成一个把网页包成 APK 的最小 Android 工程 (WebView)。由 GitHub Actions 调用。"""
import os, shutil, json

repo = os.environ.get("GITHUB_REPOSITORY", "jxy418138-beep/Wuthering-Waves-Welfare-Statistics")
owner, name = repo.split("/")
URL = "file:///android_asset/index.html"   # 网页打包进 APK，不再跳转到网站
RAW = "https://raw.githubusercontent.com/%s/%s/main/data.json" % (owner, name)   # 联网时刷新最新数据

def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

w("android/settings.gradle", """pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "wuwa"
include ":app"
""")
w("android/build.gradle", """plugins { id 'com.android.application' version '8.5.2' apply false }
""")
w("android/gradle.properties", "org.gradle.jvmargs=-Xmx2g\n")
w("android/app/build.gradle", """plugins { id 'com.android.application' }
android {
    namespace 'com.wuwa.welfare'
    compileSdk 34
    defaultConfig {
        applicationId 'com.wuwa.welfare'
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName '1.0'
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}
""")
w("android/app/src/main/AndroidManifest.xml", """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET"/>
    <application
        android:label="鸣潮福利"
        android:icon="@drawable/ic_launcher"
        android:theme="@android:style/Theme.DeviceDefault.NoActionBar">
        <activity android:name=".MainActivity" android:exported="true"
            android:configChanges="orientation|screenSize|keyboardHidden">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
    </application>
</manifest>
""")
w("android/app/src/main/java/com/wuwa/welfare/MainActivity.java", """package com.wuwa.welfare;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    static final String HOME = "%s";
    WebView web;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if ("file".equals(u.getScheme())) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, u));
                return true;
            }
        });
        web.loadUrl(HOME);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
""" % URL)

# 把网页和当前 data.json 一起打包进 APK 的 assets
html = open("index.html", encoding="utf-8").read()
data = open("data.json", encoding="utf-8").read() if os.path.exists("data.json") else "null"
data = data.replace("</", "<\\/")
old_head = "<script>\nconst $="
old_fetch = 'fetch("data.json?t="+Date.now())'
assert old_head in html and old_fetch in html, "index.html 版本不对，请重新上传最新的 index.html"
new_fetch = ('if(window.RAW){if(window.EMBED)render(window.EMBED);'
             'fetch(window.RAW+"?t="+Date.now()).then(r=>r.ok?r.json():Promise.reject()).then(render)'
             '.catch(()=>{if(!window.EMBED){$("app").innerHTML=\'<div class="mut">暂无数据，请联网后重新打开。</div>\'}})}'
             'else fetch("data.json?t="+Date.now())')
html = html.replace(old_fetch, new_fetch, 1)
html = html.replace(old_head, "<script>window.EMBED=%s;window.RAW=%s;</script>\n" % (data, json.dumps(RAW)) + old_head, 1)
w("android/app/src/main/assets/index.html", html)

# 图标：仓库里有 icon.png 就用它，否则用纯色矢量图标
if os.path.exists("icon.png"):
    os.makedirs("android/app/src/main/res/drawable", exist_ok=True)
    shutil.copy("icon.png", "android/app/src/main/res/drawable/ic_launcher.png")
else:
    w("android/app/src/main/res/drawable/ic_launcher.xml", """<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#2F6DF6" android:pathData="M0,0h108v108h-108z"/>
    <path android:fillColor="#FFFFFF" android:pathData="M54,54m-28,0a28,28 0,1 1,56 0a28,28 0,1 1,-56 0"/>
</vector>
""")
print("已生成 android/ 工程，内置网页，在线刷新地址:", RAW)
