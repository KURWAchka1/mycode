package app.playerokmonitor;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class SettingsActivity extends Activity {
    private static final int REQ_NOTIFICATIONS = 5002;
    private EditText urlInput;
    private TextView statusText;
    private final ExecutorService network = Executors.newSingleThreadExecutor();

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState); NotificationHelper.ensureChannels(this); setContentView(buildUi()); requestNotificationPermissionIfNeeded(); refreshStatus();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this); scroll.setBackgroundColor(Ui.BG);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        int p = Ui.dp(this, 18); root.setPadding(p,p,p,p);
        scroll.addView(root, new ScrollView.LayoutParams(ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left=p,top=p,right=p,bottom=p;
            if (Build.VERSION.SDK_INT >= 30) { Insets bars=insets.getInsets(WindowInsets.Type.systemBars()); left+=bars.left;top+=bars.top;right+=bars.right;bottom+=bars.bottom; }
            else { left+=insets.getSystemWindowInsetLeft();top+=insets.getSystemWindowInsetTop();right+=insets.getSystemWindowInsetRight();bottom+=insets.getSystemWindowInsetBottom(); }
            v.setPadding(left,top,right,bottom); return insets;
        });
        LinearLayout head = new LinearLayout(this); head.setOrientation(LinearLayout.HORIZONTAL); head.setGravity(Gravity.CENTER_VERTICAL); root.addView(head, matchWrap());
        Button back=button("←"); back.setOnClickListener(v->finish()); head.addView(back,new LinearLayout.LayoutParams(Ui.dp(this,52),Ui.dp(this,48)));
        TextView title=Ui.text(this,"Настройки",26,Ui.TEXT,true); LinearLayout.LayoutParams titleParams=new LinearLayout.LayoutParams(0,LinearLayout.LayoutParams.WRAP_CONTENT,1f); titleParams.leftMargin=Ui.dp(this,10); head.addView(title,titleParams);
        TextView subtitle=Ui.text(this,"Pairing URL остаётся тем же. Через него приложение получает уведомления и список заказов.",14,Ui.MUTED,false); LinearLayout.LayoutParams sub=matchWrap();sub.topMargin=Ui.dp(this,14);root.addView(subtitle,sub);
        LinearLayout card=new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);card.setPadding(Ui.dp(this,16),Ui.dp(this,16),Ui.dp(this,16),Ui.dp(this,16));card.setBackground(Ui.roundedStroke(this,Ui.CARD,Ui.BORDER,16)); LinearLayout.LayoutParams cp=matchWrap();cp.topMargin=Ui.dp(this,16);root.addView(card,cp);
        TextView label=new TextView(this);label.setText("Pairing URL");label.setTextColor(Ui.TEXT);label.setTypeface(Typeface.DEFAULT,Typeface.BOLD);card.addView(label);
        urlInput=new EditText(this);urlInput.setSingleLine(false);urlInput.setMinLines(2);urlInput.setHint("https://example.com/poll?token=...&after=");urlInput.setText(Prefs.getUrl(this));urlInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI|android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);card.addView(urlInput,matchWrap());
        Button saveStart=button("Сохранить и запустить мониторинг");saveStart.setOnClickListener(v->saveAndStart());card.addView(saveStart,marginTop(14));
        Button health=button("Проверить соединение с VPS");health.setOnClickListener(v->checkServer(false));card.addView(health,marginTop(8));
        Button test=button("Тестовое уведомление");test.setOnClickListener(v->checkServer(true));card.addView(test,marginTop(8));
        Button stop=button("Остановить мониторинг");stop.setOnClickListener(v->stopMonitoring());card.addView(stop,marginTop(8));
        Button ns=button("Настройки звука уведомлений");ns.setOnClickListener(v->openNotificationSettings());card.addView(ns,marginTop(8));
        statusText=Ui.text(this,"",14,Ui.MUTED,false);statusText.setPadding(0,Ui.dp(this,18),0,0);card.addView(statusText);
        TextView note=Ui.text(this,"Список заказов не опрашивает Playerok. Приложение читает только локальную SQLite-базу на VPS, поэтому нагрузка минимальна.",13,Ui.MUTED,false);LinearLayout.LayoutParams np=matchWrap();np.topMargin=Ui.dp(this,16);root.addView(note,np);
        return scroll;
    }

    private LinearLayout.LayoutParams matchWrap(){return new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,LinearLayout.LayoutParams.WRAP_CONTENT);} private LinearLayout.LayoutParams marginTop(int d){LinearLayout.LayoutParams p=matchWrap();p.topMargin=Ui.dp(this,d);return p;}
    private Button button(String t){Button b=new Button(this);b.setText(t);b.setAllCaps(false);b.setMinHeight(Ui.dp(this,50));return b;}
    private void saveAndStart(){String url=urlInput.getText().toString().trim();String validation=UrlTools.validatePairingUrl(url);if(validation!=null){toast(validation);return;}if(!notificationsAllowed()){requestNotificationPermissionIfNeeded();toast("Разрешите уведомления и нажмите запуск ещё раз");return;}Prefs.setUrl(this,url);Prefs.setEnabled(this,true);startForegroundService(new Intent(this,MonitorService.class).setAction(MonitorService.ACTION_START));refreshStatus();toast("Мониторинг запущен");}
    private void stopMonitoring(){Prefs.setEnabled(this,false);startService(new Intent(this,MonitorService.class).setAction(MonitorService.ACTION_STOP));refreshStatus();toast("Мониторинг остановлен");}
    private void checkServer(boolean createTest){String url=urlInput.getText().toString().trim();String validation=UrlTools.validatePairingUrl(url);if(validation!=null){toast(validation);return;}Prefs.setUrl(this,url);statusText.setText(createTest?"Создаю тестовое событие…":"Проверяю HTTPS…");network.execute(()->{try{String target=createTest?UrlTools.testUrl(url):UrlTools.healthUrl(url);String response=HttpTextClient.get(target,15_000);runOnUiThread(()->{statusText.setText("VPS ответил: "+response);if(createTest&&!Prefs.isEnabled(this))toast("Тест поставлен в очередь. Запустите мониторинг, чтобы получить уведомление.");});}catch(Exception e){runOnUiThread(()->statusText.setText("Ошибка VPS: "+e.getMessage()));}});}
    private void openNotificationSettings(){startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE,getPackageName()));}
    private boolean notificationsAllowed(){if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return false;return getSystemService(NotificationManager.class).areNotificationsEnabled();}
    private void requestNotificationPermissionIfNeeded(){if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},REQ_NOTIFICATIONS);}
    private void refreshStatus(){if(statusText!=null)statusText.setText(Prefs.isEnabled(this)?"Статус: мониторинг включён":"Статус: мониторинг выключен");}
    @Override protected void onResume(){super.onResume();refreshStatus();} @Override protected void onDestroy(){network.shutdownNow();super.onDestroy();} private void toast(String t){Toast.makeText(this,t,Toast.LENGTH_LONG).show();}
}
