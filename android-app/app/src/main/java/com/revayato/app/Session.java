package com.revayato.app;

import android.content.*;import org.json.*;import java.io.*;import java.net.*;import java.nio.charset.StandardCharsets;

/**
 * The one owner of the stored session.
 *
 * The access token the API hands out lives about an hour; the refresh token lives
 * for months. Every screen used to read the access token straight out of
 * SharedPreferences and never renew it, so an hour after signing in the app kept
 * presenting a dead token — and because most catalog endpoints also answer
 * anonymous callers, requests came back as public data instead of failing. That
 * looks exactly like "it logged me out". {@link #renew} closes that hole, and
 * {@link #call} applies it automatically on the first 401.
 */
public final class Session{
 static final String API=Config.API_BASE;
 private static final Object RENEW_LOCK=new Object();
 private Session(){}

 static SharedPreferences prefs(Context c){return c.getSharedPreferences("session",0);}
 static String token(Context c){return prefs(c).getString("token","");}
 static String refreshToken(Context c){return prefs(c).getString("refresh","");}
 /** A stored refresh token still counts: the access token can be rebuilt from it. */
 static boolean signedIn(Context c){return !token(c).isEmpty()||!refreshToken(c).isEmpty();}

 static JSONObject user(Context c){try{return new JSONObject(prefs(c).getString("user","{}"));}catch(Exception e){return new JSONObject();}}

 /** Persist whatever of {access, refresh, user} a login/refresh response carried. */
 static void save(Context c,JSONObject j){if(j==null)return;SharedPreferences.Editor e=prefs(c).edit();
  String access=j.optString("access");if(!access.isEmpty())e.putString("token",access);
  String refresh=j.optString("refresh");if(!refresh.isEmpty())e.putString("refresh",refresh);
  JSONObject user=j.optJSONObject("user");if(user!=null)e.putString("user",user.toString());
  e.apply();}

 static void clear(Context c){prefs(c).edit().remove("token").remove("refresh").remove("user").apply();}

 /**
  * Trade the refresh token for a fresh access token. Returns the new token, or
  * "" when there is nothing to trade or the server rejected it.
  *
  * Serialised on {@link #RENEW_LOCK} so two screens hitting 401 at the same
  * moment cannot both spend the refresh token — the API blacklists it on use, so
  * the loser of that race would otherwise destroy a live session. The second
  * caller re-reads storage first and takes the winner's token.
  */
 static String renew(Context c){
  synchronized(RENEW_LOCK){
   String before=token(c),refresh=refreshToken(c);
   if(refresh.isEmpty())return "";
   HttpURLConnection connection=null;
   try{
    connection=(HttpURLConnection)new URL(API+"auth/token/refresh/").openConnection();
    connection.setRequestMethod("POST");connection.setDoOutput(true);
    connection.setConnectTimeout(12000);connection.setReadTimeout(18000);
    connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
    connection.setRequestProperty("Accept","application/json");
    connection.setRequestProperty("User-Agent","RevayatoAndroid/5.0");
    try(OutputStream out=connection.getOutputStream()){out.write(new JSONObject().put("refresh",refresh).toString().getBytes(StandardCharsets.UTF_8));}
    int code=connection.getResponseCode();
    String raw=body(code<400?connection.getInputStream():connection.getErrorStream());
    if(code>=400){
     // Only a token the server calls dead ends the session. `refresh_token_rotated`
     // means it was already spent — by a racing request, or by this account on
     // another device — and a stored token that merely lost a race is not proof
     // the user logged out. Offline, rate limit and 5xx leave everything alone
     // too, so the next attempt can succeed.
     if((code==401||code==403)&&!"refresh_token_rotated".equals(codeOf(raw)))clear(c);
     return "";
    }
    JSONObject result=new JSONObject(raw);
    save(c,result);
    String access=result.optString("access");
    return access.isEmpty()?"":access;
   }catch(Exception e){
    // A racing caller may have refreshed while we were on the wire.
    String now=token(c);
    return now.isEmpty()||now.equals(before)?"":now;
   }finally{if(connection!=null)connection.disconnect();}
  }
 }

 /** Response of an authenticated call: HTTP status plus the raw body. */
 static final class Reply{
  final int code;final String raw;
  Reply(int code,String raw){this.code=code;this.raw=raw;}
  boolean ok(){return code>=200&&code<400;}
  /**
   * DRF puts human-readable failures in `detail`, and field errors in
   * `{field: ["…"]}`; either is safe to show. Anything else — a Cloudflare 502
   * page, an nginx error, a truncated response — is not a message for a user, so
   * it becomes a generic Persian line instead of a screenful of HTML.
   */
  String message(){
   try{JSONObject j=new JSONObject(raw);String detail=j.optString("detail");if(!detail.isEmpty())return detail;
    java.util.Iterator<String> keys=j.keys();
    if(keys.hasNext()){String key=keys.next();Object value=j.get(key);
     if(value instanceof JSONArray&&((JSONArray)value).length()>0)return ((JSONArray)value).optString(0);
     String text=String.valueOf(value);if(!text.isEmpty())return text;}
   }catch(Exception ignored){}
   if(code==401||code==403)return "برای این کار باید وارد حساب شوید";
   if(code==404)return "این محتوا پیدا نشد";
   if(code==429)return "درخواست‌ها زیاد شد؛ چند لحظه بعد دوباره تلاش کنید";
   if(code>=500)return "سرور در دسترس نیست؛ کمی بعد دوباره تلاش کنید";
   return "درخواست انجام نشد ("+code+")";}
 }

 /**
  * Authenticated request with a single transparent retry: if the access token has
  * expired, renew it and replay the call once. Blocking — callers run it on their
  * own executor.
  */
 static Reply call(Context c,String method,String url,JSONObject payload)throws IOException{
  Reply first=send(c,method,url,payload,token(c));
  if(first.code!=401||!signedIn(c))return first;
  String renewed=renew(c);
  return renewed.isEmpty()?first:send(c,method,url,payload,renewed);
 }

 /**
  * Deliberately anonymous request — no Authorization header, no refresh retry.
  * Login, registration and password reset must not carry a stale access token:
  * the server would answer 401 for the wrong reason and the retry path could
  * spend a refresh token the user is about to replace anyway.
  */
 static Reply post(Context c,String url,JSONObject payload)throws IOException{return send(c,"POST",url,payload,"");}

 private static Reply send(Context c,String method,String url,JSONObject payload,String token)throws IOException{
  HttpURLConnection connection=null;
  try{
   connection=(HttpURLConnection)new URL(url).openConnection();
   connection.setRequestMethod(method);
   connection.setConnectTimeout(15000);connection.setReadTimeout(30000);
   connection.setRequestProperty("Accept","application/json");
   connection.setRequestProperty("User-Agent","RevayatoAndroid/5.0");
   connection.setRequestProperty("Referer",Config.REFERER);
   if(!token.isEmpty())connection.setRequestProperty("Authorization","Bearer "+token);
   if(payload!=null){connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
    try(OutputStream out=connection.getOutputStream()){out.write(payload.toString().getBytes(StandardCharsets.UTF_8));}}
   int code=connection.getResponseCode();
   return new Reply(code,body(code<400?connection.getInputStream():connection.getErrorStream()));
  }finally{if(connection!=null)connection.disconnect();}
 }

 private static String body(InputStream in)throws IOException{
  if(in==null)return "";
  try(ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buffer=new byte[4096];
   for(int n;(n=in.read(buffer))>0;)out.write(buffer,0,n);
   return new String(out.toByteArray(),StandardCharsets.UTF_8);}
 }

 /** SimpleJWT's machine-readable failure code, when the body carries one. */
 private static String codeOf(String raw){try{return new JSONObject(raw).optString("code");}catch(Exception e){return "";}}
}
