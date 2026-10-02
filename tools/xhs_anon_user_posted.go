package main

import (
    "context"
    "fmt"
    "net/http"
    "os"
    "time"

    xhs "github.com/tamnd/xiaohongshu-cli/xiaohongshu"
)

func main() {
    if len(os.Args) < 4 {
        fmt.Fprintln(os.Stderr, "usage: probe <user_id> <xsec_token> <xsec_source>")
        os.Exit(2)
    }
    cfg := xhs.DefaultConfig()
    cfg.NoCache = true
    cfg.Rate = 1200 * time.Millisecond
    cfg.Retries = 1
    cfg.Timeout = 30 * time.Second
    c := xhs.NewClient(cfg)
    params := map[string]string{
        "num": "30",
        "cursor": "",
        "user_id": os.Args[1],
        "image_formats": "jpg,webp,avif",
        "xsec_token": os.Args[2],
        "xsec_source": os.Args[3],
    }
    b, err := c.Raw(context.Background(), http.MethodGet, "/api/sns/web/v1/user_posted", params, nil)
    if err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    os.Stdout.Write(b)
}
