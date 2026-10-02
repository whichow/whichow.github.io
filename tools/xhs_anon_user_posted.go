package main

import (
    "context"
    "fmt"
    "net/http"
    "net/url"
    "os"
    "regexp"
    "strings"
    "time"

    xhs "github.com/tamnd/xiaohongshu-cli/xiaohongshu"
)

var profileRE = regexp.MustCompile(`/user/profile/([0-9A-Za-z]+)`)

func main() {
    if len(os.Args) < 2 {
        fmt.Fprintln(os.Stderr, "usage: probe <xiaohongshu-profile-share-url>")
        os.Exit(2)
    }
    shareURL := os.Args[1]
    req, _ := http.NewRequest(http.MethodGet, shareURL, nil)
    req.Header.Set("User-Agent", xhs.DefaultUserAgent)
    hc := &http.Client{Timeout: 25 * time.Second}
    resp, err := hc.Do(req)
    if err != nil {
        fmt.Fprintln(os.Stderr, "resolve:", err)
        os.Exit(1)
    }
    resp.Body.Close()
    target := resp.Request.URL.String()
    u, _ := url.Parse(target)
    if strings.Contains(u.Path, "/login") {
        if rp := u.Query().Get("redirectPath"); rp != "" {
            target = rp
            u, _ = url.Parse(target)
        }
    }
    m := profileRE.FindStringSubmatch(u.Path)
    if len(m) < 2 {
        fmt.Fprintln(os.Stderr, "resolved target is not a profile:", target)
        os.Exit(1)
    }
    userID := m[1]
    token := u.Query().Get("xsec_token")
    source := u.Query().Get("xsec_source")
    if source == "" { source = "app_share" }
    if token == "" {
        fmt.Fprintln(os.Stderr, "profile share did not provide xsec_token")
        os.Exit(1)
    }

    cfg := xhs.DefaultConfig()
    cfg.NoCache = true
    cfg.Rate = 1200 * time.Millisecond
    cfg.Retries = 1
    cfg.Timeout = 30 * time.Second
    c := xhs.NewClient(cfg)
    params := map[string]string{
        "num": "30", "cursor": "", "user_id": userID,
        "image_formats": "jpg,webp,avif",
        "xsec_token": token, "xsec_source": source,
    }
    b, err := c.Raw(context.Background(), http.MethodGet, "/api/sns/web/v1/user_posted", params, nil)
    if err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    os.Stdout.Write(b)
}
