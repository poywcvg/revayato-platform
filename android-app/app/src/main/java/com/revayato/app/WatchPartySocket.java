package com.revayato.app;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import androidx.annotation.Nullable;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.TimeUnit;

/**
 * Authenticated watch-party socket client.
 *
 * The server authenticates via the WebSocket subprotocol `watchparty.jwt.<token>`
 * (see apps/watchparty/auth.py) and only the host may drive playback. Guests
 * receive `playback.state` / `playback.sync.response` events and reconcile their
 * local player; the host emits `playback.play/pause/seek/sync` (throttled) and a
 * periodic `playback.sync` so late joiners converge.
 */
public final class WatchPartySocket{
  /** All callbacks run on the main thread so callers can touch the player directly. */
  public interface Listener{
    void onOpen();
    void onPlaybackState(boolean playing,long positionSeconds,long durationSeconds);
    void onSyncResponse(boolean playing,long positionSeconds);
    void onError(String code,String message);
    void onClosed();
    /** Fired when the socket drops and an automatic reconnect attempt is in flight. */
    void onReconnecting();
  }

  private static final long SEND_THROTTLE_MS=600;
  private static final long SYNC_INTERVAL_MS=5000;
  private static final long HEARTBEAT_MS=20000;

  private final String code;
  private final Context context;
  private final Listener listener;
  private final Handler main=new Handler(Looper.getMainLooper());
  private final OkHttpClient client;
  private WebSocket ws;
  private boolean open;
  private long lastSend;
  private Runnable syncTimer,heartbeatTimer;

  public WatchPartySocket(Context context,String inviteCode,Listener listener){
    this.context=context.getApplicationContext();
    this.code=inviteCode;
    this.listener=listener;
    this.client=new OkHttpClient.Builder()
      .pingInterval(20,TimeUnit.SECONDS)
      .connectTimeout(15,TimeUnit.SECONDS)
      .readTimeout(0,TimeUnit.SECONDS)
      .build();
  }

  public void connect(){
    final String token=Session.token(context);
    if(token.isEmpty()){main.post(()->listener.onError("unauthorized","ابتدا وارد حساب شوید"));return;}
    Request request=new Request.Builder()
      .url(Config.WS_BASE+"watch-party/"+code+"/")
      .addHeader("Sec-WebSocket-Protocol","watchparty.jwt."+token)
      .build();
    ws=client.newWebSocket(request,new Delegate());
  }

  /** Host: request that playback resume. */
  public void sendPlay(long positionSeconds){
    if(canSend())sendEvent("playback.play",positionSeconds,0,true);
  }

  /** Host: request that playback pause. */
  public void sendPause(long positionSeconds){
    if(canSend())sendEvent("playback.pause",positionSeconds,0,false);
  }

  /** Host: request a seek to the given position (seconds). */
  public void sendSeek(long positionSeconds,long durationSeconds,boolean playing){
    if(canSend())sendEvent("playback.seek",positionSeconds,durationSeconds,playing);
  }

  /** Host: broadcast authoritative state (used by the periodic sync timer). */
  public void sendSync(long positionSeconds,long durationSeconds,boolean playing){
    if(canSend())sendEvent("playback.sync",positionSeconds,durationSeconds,playing);
  }

  /** Guest or host: ask the room for the current authoritative state. */
  public void requestSync(){
    sendRaw("{\"type\":\"playback.sync.request\"}");
  }

  public void heartbeat(){
    sendRaw("{\"type\":\"heartbeat\"}");
  }

  public void leaveAndClose(){
    sendRaw("{\"type\":\"room.leave\"}");
    close();
  }

  public void close(){
    cancelTimers();
    if(ws!=null){
      try{ws.close(1000,null);}catch(Exception ignored){}
      ws=null;
    }
  }

  public boolean isOpen(){return open;}

  /** Start the host's periodic sync broadcast + heartbeat. */
  void startHostTimers(){
    cancelTimers();
    syncTimer=new Runnable(){public void run(){if(open)sendSync(lastPosition,lastDuration,lastPlaying);main.postDelayed(this,SYNC_INTERVAL_MS);}};
    heartbeatTimer=new Runnable(){public void run(){if(open)heartbeat();main.postDelayed(this,HEARTBEAT_MS);}};
    main.postDelayed(syncTimer,SYNC_INTERVAL_MS);
    main.postDelayed(heartbeatTimer,HEARTBEAT_MS);
  }

  private void cancelTimers(){
    if(syncTimer!=null)main.removeCallbacks(syncTimer);
    if(heartbeatTimer!=null)main.removeCallbacks(heartbeatTimer);
    syncTimer=null;heartbeatTimer=null;
  }

  private boolean canSend(){
    if(!open||ws==null)return false;
    long now=System.currentTimeMillis();
    if(now-lastSend<SEND_THROTTLE_MS)return false;
    lastSend=now;
    return true;
  }

  private long lastPosition;private long lastDuration;private boolean lastPlaying;

  private void sendEvent(String type,long position,long duration,boolean playing){
    lastPosition=position;lastDuration=duration;lastPlaying=playing;
    sendRaw("{\"type\":\""+type+"\",\"position_seconds\":"+position+",\"duration_seconds\":"+duration+",\"is_playing\":"+playing+"}");
  }

  private void sendRaw(String json){
    if(open&&ws!=null){
      try{ws.send(json);}catch(Exception ignored){}
    }
  }

  private void handleMessage(String text){
    try{
      JSONObject j=new JSONObject(text);
      String type=j.optString("type","");
      if("playback.state".equals(type)||"playback.sync.response".equals(type)){
        JSONObject ps=j.optJSONObject("playback_state");
        if(ps==null&&"playback.state".equals(type))ps=j.optJSONObject("playback");
        if(ps==null)return;
        boolean playing=ps.optBoolean("is_playing",ps.optBoolean("isPlaying",false));
        long pos=(long)ps.optDouble("position_seconds",ps.optDouble("positionSeconds",0));
        long dur=(long)ps.optDouble("duration_seconds",ps.optDouble("durationSeconds",0));
        if("playback.sync.response".equals(type))listener.onSyncResponse(playing,pos);
        else listener.onPlaybackState(playing,pos,dur);
      }else if("error".equals(type)){
        String code=j.optString("code","");
        String message=j.optString("message","");
        listener.onError(code,message);
        if("token_expired".equals(code)||"unauthorized".equals(code)
          ||"4401".equals(code)||"4403".equals(code)){
          reconnect();
        }
      }
    }catch(Exception ignored){}
  }

  private void reconnect(){
    if(ws!=null){try{ws.cancel();}catch(Exception ignored){}ws=null;}
    open=false;
    String refreshed=Session.renew(context);
    if(refreshed.isEmpty()){close();return;}
    connect();
  }

  private final class Delegate extends WebSocketListener{
    @Override public void onOpen(WebSocket webSocket,Response response){
      open=true;
      main.post(()->listener.onOpen());
      requestSync();
    }
    @Override public void onMessage(WebSocket webSocket,String text){handleMessage(text);}
    @Override public void onMessage(WebSocket webSocket,okio.ByteString bytes){try{handleMessage(bytes.utf8());}catch(Exception ignored){}}
    @Override public void onFailure(WebSocket webSocket,Throwable t,@Nullable Response response){
      open=false;
      // Network drop: try the refresh+reconnect path once before giving up.
      if(!reconnecting){
        reconnecting=true;
        main.post(()->listener.onReconnecting());
        reconnect();
        reconnecting=false;
      }
      else main.post(()->listener.onClosed());
    }
    @Override public void onClosed(WebSocket webSocket,int code,String reason){
      open=false;
      main.post(()->listener.onClosed());
    }
  }

  private boolean reconnecting=false;
}
