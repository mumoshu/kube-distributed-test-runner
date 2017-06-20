package main

import (
	"database/sql"
	"encoding/base64"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
	"github.com/jmoiron/sqlx"
	"golang.org/x/oauth2"

	"crypto/rand"
	_ "github.com/go-sql-driver/mysql"
	"net/http"
	"strings"
	"io/ioutil"
)

var schema = []string{
	`CREATE TABLE IF NOT EXISTS sessions (
    id int NOT NULL AUTO_INCREMENT,
    created_at timestamp,
    PRIMARY KEY (id)
)`,
	`CREATE TABLE IF NOT EXISTS  authz_assertions (
    id int NOT NULL AUTO_INCREMENT,
    session_id int NOT NULL,
    http_request_method text,
    http_request_url text,
    created_at timestamp,
    PRIMARY KEY (id)
)`,
	`CREATE TABLE IF NOT EXISTS  authz_requests (
    id int NOT NULL AUTO_INCREMENT,
    session_id int NOT NULL ,
    oauth2_client_id text,
    oauth2_client_secret text,
    oauth2_authz_endpoint_url text,
    oauth2_token_endpoint_url text,
    oauth2_scopes text,
    created_at timestamp,
    PRIMARY KEY (id)
)`,
	// The second timestamp requires `NULL DEFAULT NULL` due to https://stackoverflow.com/a/37420863
	`CREATE TABLE IF NOT EXISTS authz_responses (
    id int NOT NULL AUTO_INCREMENT,
    session_id int NOT NULL ,
    oauth2_access_token text,
    oauth2_access_token_type text,
    oauth2_access_token_expiry timestamp NULL DEFAULT NULL,
    oauth2_refresh_token text,
    created_at timestamp NULL DEFAULT NULL,
    PRIMARY KEY (id)
)`,
}

type Session struct {
	Id        int       `db:"id"`
	CreatedAt time.Time `db:"created_at"`
}

// * /oauth2/callback is restricted by session id
type AuthzAssertion struct {
	Id                int       `db:"id"`
	SessionId         int       `db:"session_id"`
	HTTPRequestMethod string    `db:"http_request_method"`
	HTTPRequestURL    string    `db:"http_request_url"`
	CreatedAt         time.Time `db:"created_at"`
}

type AuthzRequest struct {
	Id                     int       `db:"id"`
	SessionId              int       `db:"session_id"`
	OAuth2ClientID         string    `db:"oauth2_client_id"`
	OAuth2ClientSecret     string    `db:"oauth2_client_secret"`
	OAuth2AuthzEndpointURL string    `db:"oauth2_authz_endpoint_url"`
	OAuth2TokenEndpointURL string    `db:"oauth2_token_endpoint_url"`
	OAuth2Scopes           string    `db:"oauth2_scopes"`
	CreatedAt              time.Time `db:"created_at"`
}

type AuthzResponse struct {
	Id                      int        `db:"id"`
	SessionId               int        `db:"session_id"`
	OAuth2AccessToken       string     `db:"oauth2_access_token"`
	OAuth2AccessTokenType   string     `db:"oauth2_access_token_type"`
	OAuth2AccessTokenExpiry *time.Time `db:"oauth2_access_token_expiry"`
	OAuth2RefreshToken      string     `db:"oauth2_refresh_token"`
	CreatedAt               time.Time  `db:"created_at"`
}

func veritySessionId() gin.HandlerFunc {
	return func(c *gin.Context) {
		session := sessions.Default(c)
		v := session.Get("id")
		if v == nil {
			msg := "session id was nil"
			c.Error(fmt.Errorf(msg, v))
			c.JSON(500, gin.H{"error": msg})
		} else {
			var id int64
			var ok bool
			if id, ok = v.(int64); !ok {
				msg := "id does't seem like an int: %+v"
				c.Error(fmt.Errorf(msg, v))
				c.JSON(500, gin.H{"error": msg})
			}
			log.Printf("session_id=%d", id)
			c.Set("session_id", id)
		}
	}
}

func randToken() string {
	b := make([]byte, 32)
	rand.Read(b)
	return base64.StdEncoding.EncodeToString(b)
}

func main() {
	redisHost := os.Getenv("REDIS_HOST")
	if redisHost == "" {
		redisHost = "localhost:6379"
	}

	redisPassword := os.Getenv("REDIS_PASSWORD")
	if redisPassword == "" {
		panic("No REDIS_PASSWORD set!")
	}

	mysqlUser := os.Getenv("MYSQL_USER")
	if mysqlUser == "" {
		panic("No MYSQL_USER set!")
	}
	mysqlPassword := os.Getenv("MYSQL_PASSWORD")
	if mysqlPassword == "" {
		panic("No MYSQL_PASSWORD set!")
	}

	mysqlHost := os.Getenv("MYSQL_HOST")
	if mysqlHost == "" {
		panic("No MYSQL_HOST set!")
	}

	router := gin.Default()
	router.LoadHTMLGlob("views/authz/test/*.tmpl")
	store, _ := sessions.NewRedisStore(10, "tcp", redisHost, redisPassword, []byte("secret"))
	router.Use(sessions.Sessions("mysession", store))

	// ?parseTime=true is required for parsing int in mysql to time.Time in golang. See https://github.com/jinzhu/gorm/issues/958
	db, err := sqlx.Connect("mysql", fmt.Sprintf("%s:%s@tcp(%s:3306)/kube_selenium?parseTime=true", mysqlUser, mysqlPassword, mysqlHost))
	if err != nil {
		log.Fatalln(err)
	}

	router.GET("/db/migrate", func(c *gin.Context) {
		results := []sql.Result{}
		for _, stmt := range schema {
			result, err := db.Exec(stmt)
			if err != nil {
				//c.Error(err)
				c.JSON(500, gin.H{
					"statement": stmt,
					"error":     err,
				})
				return
			}
			results = append(results, result)
		}
		c.JSON(200, gin.H{"results": results})
	})

	router.GET("/session/new", func(c *gin.Context) {
		session := sessions.Default(c)
		session.Clear()
		tx := db.MustBegin()
		result := tx.MustExec("INSERT INTO sessions (created_at) VALUES (current_timestamp)")
		if err := tx.Commit(); err != nil {
			c.Error(err)
			c.JSON(500, gin.H{"error": err})
			return
		}
		id, err := result.LastInsertId()
		if err != nil {
			panic(err)
		}
		session.Set("id", id)
		session.Save()
		c.Redirect(302, "/authz/test")
	})

	router.GET("/authz/test", veritySessionId(), func(c *gin.Context) {
		c.HTML(http.StatusOK, "authz/test/new.html.tmpl", gin.H{"title": "New test case"})
	})

	router.POST("/authz/test", veritySessionId(), func(c *gin.Context) {
		v, _ := c.Get("session_id")
		sessionID := v.(int64)

		clientID := c.PostForm("oauth2_client_id")
		clientSecret := c.PostForm("oauth2_client_secret")
		authzEndpointURL := c.PostForm("oauth2_authz_endpoint_url")
		tokenEndpointURL := c.PostForm("oauth2_token_endpoint_url")
		scopes := c.PostForm("oauth2_scopes")
		tx := db.MustBegin()
		tx.MustExec(
			"INSERT INTO authz_requests (session_id, oauth2_client_id, oauth2_client_secret, oauth2_authz_endpoint_url, oauth2_token_endpoint_url, oauth2_scopes, created_at) VALUES (?, ?, ?, ?, ?, ?, current_timestamp)",
			sessionID,
			clientID,
			clientSecret,
			authzEndpointURL,
			tokenEndpointURL,
			scopes,
		)
		tx.MustExec(
			"INSERT INTO authz_assertions (session_id, http_request_method, http_request_url, created_at) VALUES (?, ?, ?, current_timestamp)",
			sessionID,
			c.PostForm("http_request_method"),
			c.PostForm("http_request_url"),
		)
		if err := tx.Commit(); err != nil {
			c.Error(err)
			c.JSON(500, gin.H{"error": err})
			return
		}

		//redirectURL := fmt.Sprintf("http://%s/authz/test/callback", c.Request.Header.Get("HOST"))

		state := randToken()
		session := sessions.Default(c)
		session.Set("state", state)
		session.Save()

		conf := &oauth2.Config{
			ClientID:     clientID,
			ClientSecret: clientSecret,
			//RedirectURL:  redirectURL,
			Scopes:       strings.Split(scopes, ","),
			Endpoint: oauth2.Endpoint{
				AuthURL:  authzEndpointURL,
				TokenURL: tokenEndpointURL,
			},
		}

		authorizationFlowBeginningURL := conf.AuthCodeURL(state)

		c.Redirect(302, authorizationFlowBeginningURL)
	})

	router.GET("/authz/test/callback", veritySessionId(), func(c *gin.Context) {
		session := sessions.Default(c)
		retrievedState := session.Get("state")
		if retrievedState != c.Query("state") {
			c.AbortWithError(http.StatusUnauthorized, fmt.Errorf("Invalid session state: %s", retrievedState))
			return
		}

		v, _ := c.Get("session_id")
		sessionID := v.(int64)

		authzRequest := AuthzRequest{}
		row := db.QueryRowx("SELECT * FROM authz_requests WHERE session_id=?", sessionID)
		if err := row.StructScan(&authzRequest); err != nil {
			c.AbortWithError(http.StatusBadRequest, err)
			return
		}

		//redirectURL := fmt.Sprintf("http://%s/authz/test/callback", c.Request.Header.Get("HOST"))
		conf := &oauth2.Config{
			ClientID:     authzRequest.OAuth2ClientID,
			ClientSecret: authzRequest.OAuth2ClientSecret,
			//RedirectURL:  redirectURL,
			Scopes:       strings.Split(authzRequest.OAuth2Scopes, ","),
			Endpoint: oauth2.Endpoint{
				AuthURL:  authzRequest.OAuth2AuthzEndpointURL,
				TokenURL: authzRequest.OAuth2TokenEndpointURL,
			},
		}

		tok, err := conf.Exchange(oauth2.NoContext, c.Query("code"))
		if err != nil {
			c.AbortWithError(http.StatusBadRequest, err)
			return
		}

		log.Printf("token = %+v", tok)

		var expiry *time.Time
		if !tok.Expiry.IsZero() {
			expiry = &tok.Expiry
		}

		tx := db.MustBegin()
		tx.MustExec(
			"INSERT INTO authz_responses (session_id, oauth2_access_token, oauth2_access_token_type, oauth2_access_token_expiry, oauth2_refresh_token, created_at) VALUES (?, ?, ?, ?, ?, current_timestamp)",
			sessionID,
			tok.AccessToken,
			tok.TokenType,
			expiry,
			tok.RefreshToken,
		)
		if err := tx.Commit(); err != nil {
			c.Error(err)
			c.JSON(500, gin.H{"error": err})
			return
		}

		if err != nil {
			panic(err)
		}

		c.Redirect(302, "/authz/test/result")
	})

	router.GET("/authz/test/result", veritySessionId(), func(c *gin.Context) {
		v, _ := c.Get("session_id")
		sessionID := v.(int64)

		authzResponse := AuthzResponse{}
		row := db.QueryRowx("SELECT * FROM authz_responses WHERE session_id=?", sessionID)
		if err := row.StructScan(&authzResponse); err != nil {
			c.AbortWithError(http.StatusBadRequest, err)
			return
		}

		authzAssertion := AuthzAssertion{}
		row2 := db.QueryRowx("SELECT * FROM authz_assertions WHERE session_id=?", sessionID)
		if err := row2.StructScan(&authzAssertion); err != nil {
			c.AbortWithError(http.StatusBadRequest, err)
			return
		}

		authzRequest := AuthzRequest{}
		row3 := db.QueryRowx("SELECT * FROM authz_requests WHERE session_id=?", sessionID)
		if err := row3.StructScan(&authzRequest); err != nil {
			c.AbortWithError(http.StatusBadRequest, err)
			return
		}

		redirectURL := fmt.Sprintf("http://%s/authz/test/callback", c.Request.Header.Get("host"))
		conf := &oauth2.Config{
			ClientID:     authzRequest.OAuth2ClientID,
			ClientSecret: authzRequest.OAuth2ClientSecret,
			RedirectURL:  redirectURL,
			Scopes:       strings.Split(authzRequest.OAuth2Scopes, ","),
			Endpoint: oauth2.Endpoint{
				AuthURL:  authzRequest.OAuth2AuthzEndpointURL,
				TokenURL: authzRequest.OAuth2TokenEndpointURL,
			},
		}

		token := &oauth2.Token{
			AccessToken:  authzResponse.OAuth2AccessToken,
			TokenType:    authzResponse.OAuth2AccessTokenType,
			RefreshToken: authzResponse.OAuth2RefreshToken,
		}

		if authzResponse.OAuth2AccessTokenExpiry != nil {
			token.Expiry = *authzResponse.OAuth2AccessTokenExpiry
		}

		log.Printf("token = %+v", token)

		httpClient := conf.Client(oauth2.NoContext, token)

		response, err := httpClient.Get(authzAssertion.HTTPRequestURL)
		if err != nil {
			c.AbortWithError(http.StatusBadRequest, err)
			return
		}

		bytes, _ := ioutil.ReadAll(response.Body)
		body := string(bytes)
		c.JSON(200, gin.H{"response": body})
	})

	router.GET("/session", veritySessionId(), func(c *gin.Context) {
		session := sessions.Default(c)
		v := session.Get("id")
		var id int64
		if v == nil {
			id = -1
		} else {
			var ok bool
			if id, ok = v.(int64); !ok {
				msg := "id does't seem like an int: %+v"
				c.Error(fmt.Errorf(msg, v))
				c.JSON(500, gin.H{"error": msg})
				return
			}
		}
		c.JSON(200, gin.H{"id": id})
	})

	router.GET("/incr", func(c *gin.Context) {
		session := sessions.Default(c)
		var count int
		v := session.Get("count")
		if v == nil {
			count = 0
		} else {
			count = v.(int)
			count++
		}
		session.Set("count", count)
		session.Save()
		c.JSON(200, gin.H{"count": count})
	})

	router.Run(":8000")
}
